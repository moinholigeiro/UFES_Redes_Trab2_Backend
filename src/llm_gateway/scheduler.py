"""Fila explícita por nó: admissão, despacho limitado por `max_inflight`, expiração e cancelamento.

Invariantes:
- nº de jobs ativos nunca excede `max_inflight`;
- nº de jobs no sistema (pendentes + ativos) nunca excede `max_inflight + max_queue`;
- admissão e reserva ocorrem no mesmo passo síncrono do event loop (sem corrida);
- todo job termina em exatamente um estado terminal, e cada um libera seu slot.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections import deque
from typing import Any

from .backends.base import Backend, Delta, Finish
from .clinical import validate_output
from .config import NodeConfig
from .jobs import RETRYABLE_CODES, Job, JobError, JobState
from .metrics import NodeStats, RequestLog, job_record

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
        self.healthy = True
        self.last_failure: str | None = None
        self._wake = asyncio.Event()
        self._dispatcher: asyncio.Task | None = None

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
        self._pending.append(job)
        self._wake.set()

    def cancel(self, job: Job, reason: str) -> None:
        if job.finished:
            return
        job.cancel_reason = reason
        if job.state is JobState.QUEUED:
            with contextlib.suppress(ValueError):
                self._pending.remove(job)
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
            while self._pending and len(self._active) < self.node.max_inflight:
                self._start(self._pending.popleft())

    def _expire_pending(self) -> None:
        now = time.monotonic()
        expired = [j for j in self._pending if now - j.enqueued_at >= self._queue_timeout_s]
        for job in expired:
            self._pending.remove(job)
            job.state = JobState.EXPIRED
            job.error_code = "queue_timeout"
            job.finished_at = now
            job.events.put_nowait(
                ("error", self._error_payload(job, "queue_timeout", "tempo máximo na fila excedido"))
            )
            self.stats.expired += 1
            self._log.write(job_record(job))

    def _start(self, job: Job) -> None:
        job.state = JobState.ACTIVE
        job.dispatched_at = time.monotonic()
        self._active[job.request_id] = job
        job.task = asyncio.create_task(self._run(job), name=f"job-{job.request_id}")

    async def _run(self, job: Job) -> None:
        try:
            async with asyncio.timeout_at(job.deadline):
                await self._stream(job)
            job.finished_at = time.monotonic()
            job.state = JobState.DONE
            self.stats.completed += 1
            self.stats.observe_service(job.service_ms() / 1000.0)
        except JobError as err:
            self._fail(job, err.code, err.message)
        except TimeoutError:
            self._fail(job, "deadline_exceeded", "prazo total da requisição excedido")
        except asyncio.CancelledError:
            job.state = JobState.CANCELLED
            self.stats.cancelled += 1
            raise
        finally:
            if job.finished_at is None:
                job.finished_at = time.monotonic()
            self._active.pop(job.request_id, None)
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
            job.completion_tokens = job.delta_count
            job.tokens_source = "deltas"

        if finish == "length":
            raise JobError("truncated", "limite de tokens atingido antes do fim da resposta")
        if finish != "stop":
            raise JobError("incomplete_stream", "stream encerrado sem conclusão")

        result: dict[str, Any] | None = None
        if job.schema is not None:
            try:
                result = validate_output(job.schema, "".join(parts))
            except ValueError as err:
                raise JobError("schema_invalid", "saída não validou contra o schema") from err
            await self._emit(job, "result", {"schema": job.schema, "data": result})
        await self._emit(
            job,
            "done",
            {
                "finish_reason": finish,
                "completion_tokens": job.completion_tokens,
                "tokens_source": job.tokens_source,
            },
        )

    async def _emit(self, job: Job, event: str, data: dict[str, Any]) -> None:
        try:
            await asyncio.wait_for(job.events.put((event, data)), timeout=self._stall_timeout_s)
        except TimeoutError as err:
            raise JobError("client_too_slow", "cliente não consumiu a saída no prazo") from err

    def _fail(self, job: Job, code: str, message: str) -> None:
        if code in {"backend_unavailable", "backend_timeout", "incomplete_stream"}:
            self.healthy = False
            self.last_failure = code
        job.state = JobState.FAILED
        job.error_code = code
        self.stats.failed += 1
        queue = job.events
        while queue.full():
            queue.get_nowait()
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
        return {
            "model": self.node.model,
            "healthy": self.healthy,
            "last_failure": self.last_failure,
            "max_inflight": self.node.max_inflight,
            "max_queue": self.node.max_queue,
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
        }
