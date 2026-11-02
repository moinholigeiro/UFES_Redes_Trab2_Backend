"""Estado de cada requisição (job) ao longo da fila e do stream."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class JobState(StrEnum):
    QUEUED = "queued"
    ACTIVE = "active"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


TERMINAL_STATES = frozenset({JobState.DONE, JobState.FAILED, JobState.CANCELLED, JobState.EXPIRED})

# Códigos que justificam nova tentativa pelo cliente (sempre como resposta nova).
RETRYABLE_CODES = frozenset(
    {
        "backend_unavailable",
        "backend_timeout",
        "backend_error",
        "incomplete_stream",
        "schema_invalid",
        "queue_timeout",
        "deadline_exceeded",
    }
)


class JobError(Exception):
    """Falha da requisição com código estável para o cliente."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _ms(start: float | None, end: float | None) -> float | None:
    if start is None or end is None:
        return None
    return round((end - start) * 1000.0, 3)


@dataclass(eq=False)
class Job:
    request_id: str
    domain: str
    prompt: str
    prompt_hash: str
    output: str
    schema: str | None
    messages: list[dict[str, str]]
    sampling: dict[str, Any]
    max_output_tokens: int
    input_chars: int
    events: asyncio.Queue
    enqueued_at: float
    deadline: float
    requested_domain: str | None = None
    user_pseudonym: str | None = None
    requested_model: str | None = None
    route_confidence: float | None = None
    complexity: str | None = None
    complexity_confidence: float | None = None
    attempt: int = 0
    attempt_nodes: list[str] = field(default_factory=list)
    attempt_enqueued_at: float | None = None
    model: str = ""
    node: str = ""
    state: JobState = JobState.QUEUED
    queue_depth_at_admission: int = 0
    dispatched_at: float | None = None
    first_delta_at: float | None = None
    last_delta_at: float | None = None
    finished_at: float | None = None
    delta_count: int = 0
    delta_buffer_dropped: int = 0
    output_chars: int = 0
    output_bytes: int = 0
    completion_tokens: int | None = None
    tokens_source: str | None = None
    finish_reason: str | None = None
    error_code: str | None = None
    cancel_reason: str | None = None
    task: asyncio.Task | None = field(default=None, repr=False)

    @property
    def finished(self) -> bool:
        return self.state in TERMINAL_STATES

    def queue_wait_ms(self) -> float | None:
        return _ms(self.attempt_enqueued_at or self.enqueued_at, self.dispatched_at)

    def ttft_ms(self) -> float | None:
        return _ms(self.enqueued_at, self.first_delta_at)

    def service_ms(self) -> float | None:
        return _ms(self.dispatched_at, self.finished_at)

    def e2e_ms(self) -> float | None:
        return _ms(self.enqueued_at, self.finished_at)

    def decode_tokens_per_s(self) -> float | None:
        """(n-1) / (t_último_delta - t_primeiro_delta); indefinido se n<2 ou intervalo nulo."""
        n = self.completion_tokens
        if n is None or n < 2 or self.first_delta_at is None or self.last_delta_at is None:
            return None
        span = self.last_delta_at - self.first_delta_at
        if span <= 0:
            return None
        return round((n - 1) / span, 3)
