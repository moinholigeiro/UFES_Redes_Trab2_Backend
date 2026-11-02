"""API HTTP do gateway (FastAPI). Um único processo/worker: filas e métricas estão em memória."""

from __future__ import annotations

import asyncio
import os
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
from .gateway import Gateway
from .jobs import Job
from .metrics import RequestLog
from .prompts import build_messages, prompt_hash
from .protocol import TERMINAL_EVENTS, GenerateRequest, sse_comment, sse_encode
from .scheduler import Overloaded

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
    yield sse_encode(
        "meta",
        {
            "request_id": job.request_id,
            "domain": job.domain,
            "model": job.model,
            "node": job.node,
            "prompt": job.prompt,
            "prompt_hash": job.prompt_hash,
            "schema": job.schema,
            "queue_depth_at_admission": job.queue_depth_at_admission,
        },
    )
    try:
        while True:
            try:
                event, data = await asyncio.wait_for(job.events.get(), timeout=heartbeat_s)
            except TimeoutError:
                if job.finished and job.events.empty():
                    return
                yield sse_comment("keepalive")
                continue
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
        async with httpx.AsyncClient(timeout=timeout) as client:
            backends = {n.name: make_backend(n, client) for n in config.nodes}
            gateway = Gateway(config, backends, RequestLog(gw_cfg.metrics_log))
            app.state.gateway = gateway
            gateway.start()
            try:
                yield
            finally:
                await gateway.stop()

    app = FastAPI(title="LLM Gateway", version="0.1.0", lifespan=lifespan)
    app.state.config = config

    @app.exception_handler(_Reject)
    async def _on_reject(_: Request, exc: _Reject) -> JSONResponse:
        return _error_response(exc.status, exc.code, exc.message, exc.headers)

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

    @app.get("/metrics")
    async def metrics() -> dict[str, Any]:
        return app.state.gateway.snapshot()

    @app.post("/v1/generate", response_model=None)
    async def generate(request: Request) -> JSONResponse | StreamingResponse:
        gateway: Gateway = app.state.gateway
        gw_cfg = config.gateway
        raw = await _read_limited(request, gw_cfg.max_request_bytes)
        try:
            req = GenerateRequest.model_validate_json(raw)
        except ValidationError:
            return _error_response(422, "invalid_request", "requisição inválida")
        dom = config.domains.get(req.domain)
        if dom is None:
            return _error_response(400, "unknown_domain", f"domínio desconhecido: {req.domain!r}")
        if len(req.input) > gw_cfg.max_input_chars:
            return _error_response(413, "input_too_large", "entrada excede o limite de caracteres")
        max_out = req.max_output_tokens or dom.default_max_output_tokens
        if max_out > dom.max_output_tokens:
            return _error_response(
                422, "max_output_tokens_exceeds_limit", "max_output_tokens acima do domínio"
            )

        now = time.monotonic()
        job = Job(
            request_id=uuid.uuid4().hex,
            domain=req.domain,
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
            deadline=now + gw_cfg.request_deadline_s,
        )
        try:
            gateway.admit(job)
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
