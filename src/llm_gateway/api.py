"""API HTTP do gateway (FastAPI). Um único processo/worker: filas e métricas estão em memória."""

from __future__ import annotations

import asyncio
import os
import ssl
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import ValidationError

from .backends import make_backend
from .config import AppConfig, load_config
from .gateway import Gateway, NoHealthyNodes
from .jobs import Job
from .metrics import RequestLog
from .prompts import build_messages, prompt_hash
from .protocol import TERMINAL_EVENTS, GenerateRequest, sse_comment, sse_encode
from .routing import RouteUncertain, SemanticRouter
from .scheduler import Overloaded
from .security import Principal, RateLimitExceeded, SecurityManager, load_credentials

CONFIG_ENV = "LLM_GATEWAY_CONFIG"


class _Reject(Exception):
    def __init__(self, status: int, code: str, message: str, headers: dict[str, str] | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.headers = headers or {}


def _error_response(
    status: int, code: str, message: str, headers: dict[str, str] | None = None
) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message}},
        headers=headers,
    )


async def _read_limited(request: Request, limit: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > limit:
            raise _Reject(413, "body_too_large", "corpo da requisição excede o limite")
        chunks.append(chunk)
    return b"".join(chunks)


async def _event_stream(
    request: Request, gateway: Gateway, job: Job, heartbeat_s: float
) -> AsyncIterator[str]:
    meta_sent = False
    try:
        while True:
            try:
                event, data = await asyncio.wait_for(job.events.get(), timeout=heartbeat_s)
            except TimeoutError:
                if job.finished and job.events.empty():
                    return
                yield sse_comment("keepalive")
                continue
            if event == "error" and not data.get("partial") and data.get("retryable"):
                attempt_task = job.task
                if attempt_task is not None:
                    await asyncio.gather(attempt_task, return_exceptions=True)
                if gateway.retry_before_first_delta(job):
                    continue
            if not meta_sent:
                yield sse_encode(
                    "meta",
                    {
                        "request_id": job.request_id,
                        "domain": job.domain,
                        "requested_domain": job.requested_domain,
                        "model": job.model,
                        "node": job.node,
                        "prompt": job.prompt,
                        "prompt_hash": job.prompt_hash,
                        "schema": job.schema,
                        "queue_depth_at_admission": job.queue_depth_at_admission,
                        "attempt": job.attempt,
                        "attempt_nodes": list(job.attempt_nodes),
                        "route_confidence": job.route_confidence,
                        "complexity": job.complexity,
                        "complexity_confidence": job.complexity_confidence,
                    },
                )
                meta_sent = True
            yield sse_encode(event, data)
            if event in TERMINAL_EVENTS:
                return
    finally:
        if not job.finished:
            gateway.cancel(job, "client_disconnected")


def create_app(config: AppConfig) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        gw_cfg = config.gateway
        timeout = httpx.Timeout(connect=5.0, read=gw_cfg.backend_read_timeout_s, write=10.0, pool=10.0)
        verify: bool | ssl.SSLContext = (
            ssl.create_default_context(cafile=str(gw_cfg.backend_ca_file)) if gw_cfg.backend_ca_file else True
        )
        async with httpx.AsyncClient(timeout=timeout, verify=verify) as client:
            backends = {n.name: make_backend(n, client) for n in config.nodes}
            gateway = Gateway(config, backends, RequestLog(gw_cfg.metrics_log))
            app.state.gateway = gateway
            app.state.security = (
                SecurityManager(load_credentials(config.security.users_file, set(config.domains)))
                if config.security.enabled and config.security.users_file is not None
                else None
            )
            app.state.router = (
                SemanticRouter(config.router.examples_file, config.domains, config.router)
                if config.router.enabled
                else None
            )
            gateway.start()

            async def probe_unhealthy_nodes() -> None:
                while True:
                    for scheduler in gateway.nodes.values():
                        if scheduler.node.kind != "llama_server" or not scheduler.node.url:
                            continue
                        try:
                            response = await client.get(
                                scheduler.node.url.rstrip("/") + "/health",
                                timeout=gw_cfg.health_check_timeout_s,
                            )
                            healthy_response = False
                            if response.status_code == 200:
                                try:
                                    payload = response.json()
                                    healthy_response = (
                                        isinstance(payload, dict) and payload.get("status") == "ok"
                                    )
                                except ValueError:
                                    healthy_response = False
                            if healthy_response:
                                scheduler.healthy = True
                                scheduler.last_failure = None
                            else:
                                scheduler.healthy = False
                                scheduler.last_failure = "health_check_failed"
                        except httpx.HTTPError:
                            pass
                    await asyncio.sleep(gw_cfg.health_check_interval_s)

            health_task = asyncio.create_task(probe_unhealthy_nodes(), name="backend-health-probe")
            try:
                yield
            finally:
                health_task.cancel()
                await asyncio.gather(health_task, return_exceptions=True)
                await gateway.stop()

    app = FastAPI(title="LLM Gateway", version="0.1.0", lifespan=lifespan)
    app.state.config = config

    @app.exception_handler(_Reject)
    async def _on_reject(_: Request, exc: _Reject) -> JSONResponse:
        return _error_response(exc.status, exc.code, exc.message, exc.headers)

    def _principal(request: Request, *, metrics: bool = False) -> Principal | None:
        manager: SecurityManager | None = getattr(request.app.state, "security", None)
        if manager is None:
            return None
        try:
            principal = manager.authenticate(request.headers.get("authorization"))
        except PermissionError as exc:
            code = str(exc)
            message = "token Bearer obrigatório" if code == "missing_token" else "token inválido"
            raise _Reject(
                401,
                code,
                message,
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc
        if metrics and not manager.allow_metrics(principal):
            raise _Reject(403, "metrics_forbidden", "usuário não autorizado a consultar métricas")
        return principal

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/v1/domains")
    async def domains() -> dict[str, Any]:
        return {
            "domains": [
                {
                    "name": name,
                    "description": dom.description,
                    "output": dom.output,
                    "schema": dom.schema_name,
                }
                for name, dom in config.domains.items()
            ]
        }

    @app.get("/metrics", response_model=None)
    async def metrics(request: Request) -> dict[str, Any] | JSONResponse:
        if config.security.require_tls and request.url.scheme != "https":
            return _error_response(426, "tls_required", "use HTTPS para acessar este endpoint")
        _principal(request, metrics=True)
        snapshot = app.state.gateway.snapshot()
        router: SemanticRouter | None = app.state.router
        if router is not None:
            snapshot["routing_evaluation"] = router.evaluation()
        return snapshot

    @app.post("/v1/generate", response_model=None)
    async def generate(request: Request) -> JSONResponse | StreamingResponse:
        request_received_at = time.monotonic()
        gateway: Gateway = app.state.gateway
        gw_cfg = config.gateway
        if config.security.require_tls and request.url.scheme != "https":
            return _error_response(426, "tls_required", "use HTTPS para acessar este endpoint")
        principal = _principal(request)
        manager: SecurityManager | None = getattr(request.app.state, "security", None)
        if principal is not None and manager is not None:
            try:
                manager.consume_request(principal)
            except RateLimitExceeded as exc:
                return _error_response(
                    429,
                    "rate_limited",
                    "limite de requisições excedido",
                    headers={"Retry-After": str(exc.retry_after_s)},
                )
        request_deadline = request_received_at + gw_cfg.request_deadline_s
        try:
            async with asyncio.timeout(15.0):
                raw = await _read_limited(request, gw_cfg.max_request_bytes)
        except TimeoutError:
            return _error_response(408, "request_body_timeout", "leitura do corpo excedeu o prazo")
        try:
            req = GenerateRequest.model_validate_json(raw)
        except ValidationError:
            return _error_response(422, "invalid_request", "requisição inválida")
        if len(req.input) > gw_cfg.max_input_chars:
            return _error_response(413, "input_too_large", "entrada excede o limite de caracteres")
        if time.monotonic() >= request_deadline:
            return _error_response(408, "deadline_exceeded", "prazo total excedido ao ler a requisição")
        router: SemanticRouter | None = app.state.router
        if req.domain == "auto" and router is None:
            return _error_response(422, "router_disabled", "roteamento auto não está habilitado")
        if req.domain != "auto" and req.domain not in config.domains:
            return _error_response(400, "unknown_domain", f"domínio desconhecido: {req.domain!r}")
        decision = None
        if router is not None and req.domain == "auto":
            try:
                decision = router.route(req.domain, req.input)
            except RouteUncertain as exc:
                return JSONResponse(
                    status_code=422,
                    content={
                        "error": {
                            "code": "domain_uncertain",
                            "message": (
                                "não foi possível identificar o domínio com confiança; "
                                "informe-o explicitamente"
                            ),
                            "candidates": [
                                {"domain": name, "confidence": confidence}
                                for name, confidence in exc.candidates
                            ],
                        }
                    },
                )
        resolved_domain = decision.domain if decision is not None else req.domain
        dom = config.domains[resolved_domain]
        if principal is not None and manager is not None:
            try:
                manager.authorize_domain(principal, resolved_domain)
            except PermissionError:
                return _error_response(403, "domain_forbidden", "usuário não autorizado para este domínio")
        max_out = req.max_output_tokens or dom.default_max_output_tokens
        if max_out > dom.max_output_tokens:
            return _error_response(
                422, "max_output_tokens_exceeds_limit", "max_output_tokens acima do domínio"
            )

        now = time.monotonic()
        deadline = request_deadline
        if now >= deadline:
            return _error_response(408, "deadline_exceeded", "prazo total excedido antes da fila")
        job = Job(
            request_id=uuid.uuid4().hex,
            domain=resolved_domain,
            prompt=dom.prompt,
            prompt_hash=prompt_hash(dom.prompt),
            output=dom.output,
            schema=dom.schema_name,
            messages=build_messages(dom.prompt, dom.output, req.input),
            sampling={"temperature": dom.temperature, "top_p": dom.top_p, "top_k": dom.top_k},
            max_output_tokens=max_out,
            input_chars=len(req.input),
            events=asyncio.Queue(maxsize=gw_cfg.event_buffer_size),
            enqueued_at=now,
            deadline=deadline,
            requested_domain=req.domain,
            user_pseudonym=principal.pseudonym if principal is not None else None,
            requested_model=(
                decision.model if decision is not None else (dom.default_model or dom.models[0])
            ),
            route_confidence=decision.domain_confidence if decision is not None else None,
            complexity=decision.complexity if decision is not None else None,
            complexity_confidence=decision.complexity_confidence if decision is not None else None,
        )
        try:
            gateway.admit(job)
        except NoHealthyNodes:
            return _error_response(
                503,
                "no_healthy_nodes",
                "nenhum nó saudável para este domínio; tente novamente",
                headers={"Retry-After": str(max(1, int(gw_cfg.health_check_interval_s)))},
            )
        except Overloaded:
            return _error_response(
                503,
                "queue_full",
                "capacidade do domínio esgotada; tente novamente",
                headers={"Retry-After": "1"},
            )
        return StreamingResponse(
            _event_stream(request, gateway, job, gw_cfg.heartbeat_interval_s),
            media_type="text/event-stream; charset=utf-8",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return app


def create_app_from_env() -> FastAPI:
    """Fábrica para `uvicorn --factory`: lê o caminho da configuração em LLM_GATEWAY_CONFIG."""
    path = os.environ.get(CONFIG_ENV)
    if not path:
        raise RuntimeError(f"defina {CONFIG_ENV} com o caminho do arquivo de configuração")
    return create_app(load_config(Path(path)))
