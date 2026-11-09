"""Fila explícita por nó: admissão, despacho limitado por `max_inflight`, expiração e cancelamento.

Invariantes:
- nº de jobs ativos nunca excede `max_inflight`;
- nº de jobs no sistema (pendentes + ativos) nunca excede `max_inflight + max_queue`;
- admissão e reserva ocorrem no mesmo passo síncrono do event loop (sem corrida);
- todo job termina em exatamente um estado terminal, e cada um libera seu slot.

A ordem de saída da fila vem de `queue_policy.py` (FIFO ou curtos primeiro). Cada mudança de posição
gera um evento `queued` para o cliente. Quando o nó fica fora do ar, o gateway é avisado pelo callback
`on_unhealthy` e migra os pedidos que ainda esperavam aqui para outra réplica.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections import deque
from collections.abc import Callable
from typing import Any

import httpx

from .backends.base import Backend, Delta, Finish
from .clinical import validate_output
from .config import NodeConfig
from .jobs import RETRYABLE_CODES, Job, JobError, JobState
from .metrics import NodeStats, RequestLog, job_record
from .queue_policy import QueuePolicy

SWEEP_INTERVAL_S = 0.5


class Overloaded(Exception):
    """Capacidade do nó esgotada: o gateway responde 503."""


class NodeScheduler:
    def __init__(
        self,
        node: NodeConfig,
        backend: Backend,
        *,
        stall_timeout_s: float,
        queue_timeout_s: float,
        log: RequestLog,
        policy: QueuePolicy | None = None,
    ) -> None:
        self.node = node
        self.name = node.name
        self.stats = NodeStats()
        self._backend = backend
        self._stall_timeout_s = stall_timeout_s
        self._queue_timeout_s = queue_timeout_s
        self._log = log
        self._pending: deque[Job] = deque()
        self._active: dict[str, Job] = {}
        self.healthy = node.kind == "simulated"
        self.last_failure: str | None = None
        self._wake = asyncio.Event()
        self._dispatcher: asyncio.Task | None = None
        self.policy = policy or QueuePolicy()
        # Chamado quando o nó passa de saudável para fora do ar (o gateway migra a fila).
        self.on_unhealthy: Callable[[NodeScheduler], None] | None = None

    def set_health(self, healthy: bool, reason: str | None = None) -> None:
        """Único ponto que muda a saúde do nó; avisa o gateway na transição para fora do ar."""
        was_healthy = self.healthy
        self.healthy = healthy
        self.last_failure = None if healthy else reason
        if was_healthy and not healthy and self.on_unhealthy is not None:
            self.on_unhealthy(self)
        if healthy and not was_healthy:
            self._wake.set()

    def pending_jobs(self) -> list[Job]:
        """Pedidos que esperam vaga, na ordem em que seriam atendidos."""
        return self.policy.ordered(self._pending, time.monotonic())

    def remove_pending(self, job: Job) -> None:
        """Tira um pedido da fila sem encerrá-lo (usado na migração para outra réplica)."""
        self._pending.remove(job)
        job.queue_position = None
        self._publish_positions()

    def _publish_positions(self) -> None:
        """Envia `queued {position}` a cada pedido cuja posição na fila mudou.

        Evento informativo: se o buffer do cliente estiver cheio, a atualização é pulada
        (a próxima mudança de posição corrige).
        """
        for index, job in enumerate(self.pending_jobs(), start=1):
            if job.queue_position == index:
                continue
            job.queue_position = index
            if not job.events.full():
                job.events.put_nowait(("queued", {"position": index, "node": self.name}))

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    @property
    def active_count(self) -> int:
        return len(self._active)

    @property
    def in_system(self) -> int:
        return len(self._pending) + len(self._active)

    def start(self) -> None:
        self._dispatcher = asyncio.create_task(self._dispatch_loop(), name=f"dispatch-{self.name}")

    async def stop(self) -> None:
        if self._dispatcher is not None:
            self._dispatcher.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._dispatcher
            self._dispatcher = None
        for job in list(self._pending):
            self.cancel(job, "shutdown")
        tasks = [job.task for job in self._active.values() if job.task is not None]
        for job in list(self._active.values()):
            self.cancel(job, "shutdown")
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def admit(self, job: Job) -> None:
        capacity = self.node.max_inflight + self.node.max_queue
        if self.in_system >= capacity:
            self.stats.rejected += 1
            raise Overloaded(self.name)
        job.node = self.name
        job.model = self.node.model
        job.attempt += 1
        job.attempt_nodes.append(self.name)
        job.attempt_enqueued_at = time.monotonic()
        job.queue_depth_at_admission = self.in_system
        job.state = JobState.QUEUED
        job.queue_position = None
        self._pending.append(job)
        self._publish_positions()
        self._wake.set()

    def cancel(self, job: Job, reason: str) -> None:
        if job.finished:
            return
        job.cancel_reason = reason
        if job.state is JobState.QUEUED:
            with contextlib.suppress(ValueError):
                self._pending.remove(job)
                self._publish_positions()
            job.state = JobState.CANCELLED
            job.finished_at = time.monotonic()
            self.stats.cancelled += 1
            self._log.write(job_record(job))
        elif job.task is not None:
            job.task.cancel()

    async def _dispatch_loop(self) -> None:
        while True:
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._wake.wait(), timeout=SWEEP_INTERVAL_S)
            self._wake.clear()
            self._expire_pending()
            if not self.healthy:
                continue
            started = False
            while self._pending and len(self._active) < self.node.max_inflight:
                now = time.monotonic()
                job = self.policy.next_job(self._pending, now)
                assert job is not None
                waited = now - (job.attempt_enqueued_at or job.enqueued_at)
                if now >= job.deadline or waited >= self._queue_timeout_s:
                    self._expire_pending()
                    continue
                self._pending.remove(job)
                job.queue_position = None
                self._start(job)
                started = True
            if started:
                self._publish_positions()

    def _expire_pending(self) -> None:
        now = time.monotonic()
        expired = [
            j
            for j in self._pending
            if now >= j.deadline or now - (j.attempt_enqueued_at or j.enqueued_at) >= self._queue_timeout_s
        ]
        for job in expired:
            self._pending.remove(job)
            job.state = JobState.EXPIRED
            code = "deadline_exceeded" if now >= job.deadline else "queue_timeout"
            job.error_code = code
            job.finished_at = now
            job.events.put_nowait(
                (
                    "error",
                    self._error_payload(
                        job,
                        code,
                        "prazo excedido enquanto aguardava na fila"
                        if code == "deadline_exceeded"
                        else "tempo máximo na fila excedido",
                    ),
                )
            )
            self.stats.expired += 1
            self._log.write(job_record(job))
        if expired:
            self._publish_positions()

    def _start(self, job: Job) -> None:
        job.state = JobState.ACTIVE
        job.dispatched_at = time.monotonic()
        self._active[job.request_id] = job
        job.task = asyncio.create_task(self._run(job), name=f"job-{job.request_id}")
        job.task.add_done_callback(lambda _task, job=job: self._release_if_never_ran(job))

    def _release_if_never_ran(self, job: Job) -> None:
        """Libera a vaga de um pedido cancelado antes de a tarefa dar o primeiro passo.

        Se o cliente desconecta no mesmo instante em que o pedido ganha a vaga, `task.cancel()`
        chega antes de `_run` começar: o asyncio descarta a corrotina sem executar o `try/finally`
        dela, e a vaga ficaria ocupada para sempre (achado no ensaio do experimento, 09/11).
        Este callback roda sempre; no caso normal, `_run` já liberou a vaga e ele não faz nada.
        """
        if self._active.pop(job.request_id, None) is None:
            return
        if not job.finished:
            job.state = JobState.CANCELLED
            job.finished_at = time.monotonic()
            self.stats.cancelled += 1
            with contextlib.suppress(Exception):
                self._log.write(job_record(job))
        self._wake.set()

    async def _run(self, job: Job) -> None:
        try:
            async with asyncio.timeout_at(job.deadline):
                await self._stream(job)
            job.finished_at = time.monotonic()
            job.state = JobState.DONE
            self.stats.completed += 1
            self.stats.observe_service(job.service_ms() / 1000.0)
            self.stats.observe_completion(job.completion_tokens)
        except JobError as err:
            self._fail(job, err.code, err.message)
        except httpx.HTTPError:
            self._fail(job, "backend_transport_error", "falha de transporte com o nó")
        except TimeoutError:
            self._fail(job, "deadline_exceeded", "prazo total da requisição excedido")
        except asyncio.CancelledError:
            job.state = JobState.CANCELLED
            self.stats.cancelled += 1
            raise
        except Exception:
            # Última barreira: um adapter/logger inesperado não pode deixar consumidor
            # esperando indefinidamente nem manter a vaga reservada.
            self._fail(job, "internal_error", "falha interna ao processar a requisição")
        finally:
            if job.finished_at is None:
                job.finished_at = time.monotonic()
            self._active.pop(job.request_id, None)
            with contextlib.suppress(Exception):
                self._log.write(job_record(job))
            self._wake.set()

    async def _stream(self, job: Job) -> None:
        parts: list[str] = []
        finish: str | None = None
        usage: dict[str, Any] | None = None
        chunks = self._backend.stream(job)
        try:
            async for chunk in chunks:
                if isinstance(chunk, Delta):
                    try:
                        output_bytes = len(chunk.text.encode("utf-8", errors="strict")) + job.output_bytes
                    except UnicodeEncodeError as err:
                        raise JobError("backend_protocol_error", "nó enviou Unicode inválido") from err
                    if output_bytes > self.node.max_output_bytes:
                        raise JobError("output_too_large", "saída excedeu o limite do gateway")
                    job.output_bytes = output_bytes
                    now = time.monotonic()
                    if job.first_delta_at is None:
                        job.first_delta_at = now
                    job.last_delta_at = now
                    job.delta_count += 1
                    job.output_chars += len(chunk.text)
                    parts.append(chunk.text)
                    await self._emit(job, "delta", {"seq": job.delta_count, "text": chunk.text})
                elif isinstance(chunk, Finish):
                    finish, usage = chunk.reason, chunk.usage
        finally:
            await chunks.aclose()

        job.finish_reason = finish
        if usage and usage.get("completion_tokens") is not None:
            job.completion_tokens = int(usage["completion_tokens"])
            job.tokens_source = "backend_usage"
        else:
            job.completion_tokens = None
            job.tokens_source = "unknown"

        # Texto cortado no limite de tokens é uma resposta válida: o `done` informa
        # finish_reason="length" e o cliente mostra que foi cortada. O experimento usa isso
        # para ter pedidos de tamanho fixo. JSON cortado é inválido, por isso continua erro.
        if finish == "length" and job.schema is not None:
            raise JobError("truncated", "limite de tokens atingido antes do fim da resposta")
        if finish not in {"stop", "length"}:
            raise JobError("incomplete_stream", "stream encerrado sem conclusão")

        result: dict[str, Any] | None = None
        if job.schema is not None:
            try:
                result = validate_output(job.schema, "".join(parts))
            except ValueError as err:
                raise JobError("schema_invalid", "saída não validou contra o schema") from err
        terminal = []
        if result is not None:
            terminal.append(("result", {"schema": job.schema, "data": result}))
        terminal.append(
            (
                "done",
                {
                    "finish_reason": finish,
                    "request_id": job.request_id,
                    "completion_tokens": job.completion_tokens,
                    "tokens_source": job.tokens_source or "unknown",
                },
            )
        )
        deadline = time.monotonic() + self._stall_timeout_s
        while job.events.maxsize - job.events.qsize() < len(terminal):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise JobError("client_too_slow", "cliente não consumiu a saída no prazo")
            await asyncio.sleep(min(0.01, remaining))
        # Publish terminal state in the same non-awaiting turn as its events so
        # disconnect/deadline cannot cancel a job after a public `done` escaped.
        job.finished_at = time.monotonic()
        job.state = JobState.DONE
        for event in terminal:
            job.events.put_nowait(event)

    async def _emit(self, job: Job, event: str, data: dict[str, Any]) -> None:
        try:
            await asyncio.wait_for(job.events.put((event, data)), timeout=self._stall_timeout_s)
        except TimeoutError as err:
            raise JobError("client_too_slow", "cliente não consumiu a saída no prazo") from err

    def _fail(self, job: Job, code: str, message: str) -> None:
        if code in {"backend_unavailable", "backend_timeout", "backend_transport_error"}:
            self.set_health(False, code)
        job.state = JobState.FAILED
        job.error_code = code
        self.stats.failed += 1
        queue = job.events
        while queue.full():
            event, _ = queue.get_nowait()
            if event == "delta":
                job.delta_buffer_dropped += 1
        queue.put_nowait(("error", self._error_payload(job, code, message)))

    @staticmethod
    def _error_payload(job: Job, code: str, message: str) -> dict[str, Any]:
        return {
            "code": code,
            "message": message,
            "partial": job.delta_count > 0,
            "retryable": code in RETRYABLE_CODES,
        }

    def snapshot(self) -> dict[str, Any]:
        now = time.monotonic()
        return {
            "model": self.node.model,
            "healthy": self.healthy,
            "last_failure": self.last_failure,
            "max_inflight": self.node.max_inflight,
            "max_queue": self.node.max_queue,
            "queue_policy": self.policy.name,
            "active": self.active_count,
            "pending": self.pending_count,
            "completed": self.stats.completed,
            "failed": self.stats.failed,
            "cancelled": self.stats.cancelled,
            "expired": self.stats.expired,
            "rejected": self.stats.rejected,
            "service_ewma_s": None
            if self.stats.service_ewma_s is None
            else round(self.stats.service_ewma_s, 4),
            "completed_tokens": self.stats.completed_tokens,
            # Pedidos ocupando vaga agora (diagnóstico de vaga presa); sem texto do pedido.
            "active_jobs": [
                {
                    "request_id": job.request_id,
                    "state": job.state.value,
                    "deltas": job.delta_count,
                    "buffered_events": job.events.qsize(),
                    "age_s": None if job.dispatched_at is None else round(now - job.dispatched_at, 1),
                }
                for job in self._active.values()
            ],
            "throughput": self.stats.throughput(),
        }
