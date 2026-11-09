"""Instrumentação: log JSONL por requisição e estatísticas por nó.

Não registra texto de entrada, saída, prompt integral, nem tokens de acesso.
Tempos usam relógio monotônico do processo; o campo `ts_wall` serve só para correlação.
"""

from __future__ import annotations

import json
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TextIO

from .jobs import Job, JobState

EWMA_ALPHA = 0.3
# Janela da vazão agregada exposta em /metrics.
THROUGHPUT_WINDOW_S = 60.0


@dataclass
class NodeStats:
    completed: int = 0
    failed: int = 0
    cancelled: int = 0
    expired: int = 0
    rejected: int = 0
    observations: int = 0
    service_ewma_s: float | None = None
    completed_tokens: int = 0
    started_at: float = field(default_factory=time.monotonic)
    # (instante de conclusão, tokens) dos pedidos concluídos na última janela
    _recent: deque[tuple[float, int]] = field(default_factory=deque, repr=False)

    def observe_completion(self, tokens: int | None, now: float | None = None) -> None:
        """Registra um pedido concluído para a vazão. Sem contagem do runtime, conta 0 tokens."""
        current = time.monotonic() if now is None else now
        count = tokens or 0
        self.completed_tokens += count
        self._recent.append((current, count))
        self._prune(current)

    def _prune(self, now: float) -> None:
        while self._recent and now - self._recent[0][0] > THROUGHPUT_WINDOW_S:
            self._recent.popleft()

    def throughput(self, now: float | None = None) -> dict[str, float]:
        """Vazão na última janela: pedidos/s e tokens/s concluídos (agregado do nó)."""
        current = time.monotonic() if now is None else now
        self._prune(current)
        span = min(THROUGHPUT_WINDOW_S, max(current - self.started_at, 1e-9))
        tokens = sum(count for _, count in self._recent)
        return {
            "window_s": round(span, 3),
            "requests_per_s": round(len(self._recent) / span, 4),
            "tokens_per_s": round(tokens / span, 3),
        }

    def observe_service(self, service_s: float) -> None:
        self.observations += 1
        if self.service_ewma_s is None:
            self.service_ewma_s = service_s
        else:
            self.service_ewma_s = (1 - EWMA_ALPHA) * self.service_ewma_s + EWMA_ALPHA * service_s


class RequestLog:
    """Anexa um registro JSON por requisição terminal (ou por tentativa)."""

    def __init__(self, path: Path | None) -> None:
        self._fh: TextIO | None = None
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            self._fh = path.open("a", encoding="utf-8")

    def write(self, record: dict[str, Any]) -> None:
        if self._fh is None:
            return
        self._fh.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
        self._fh.flush()

    def close(self) -> None:
        if self._fh is not None:
            self._fh.close()
            self._fh = None


def job_record(job: Job) -> dict[str, Any]:
    partial_discarded = job.state is not JobState.DONE and job.delta_count > 0
    return {
        "ts_wall": round(time.time(), 3),
        "request_id": job.request_id,
        "domain": job.domain,
        "requested_domain": job.requested_domain,
        "user_pseudonym": job.user_pseudonym,
        "model": job.model,
        "requested_model": job.requested_model,
        "route_confidence": job.route_confidence,
        "complexity": job.complexity,
        "complexity_confidence": job.complexity_confidence,
        "node": job.node,
        "attempt": job.attempt,
        "attempt_nodes": list(job.attempt_nodes),
        "prompt": job.prompt,
        "prompt_hash": job.prompt_hash,
        "schema": job.schema,
        "status": job.state.value,
        "error_code": job.error_code,
        "cancel_reason": job.cancel_reason,
        "finish_reason": job.finish_reason,
        "input_chars": job.input_chars,
        "output_chars": job.output_chars,
        "max_output_tokens": job.max_output_tokens,
        "delta_count": job.delta_count,
        "delta_buffer_dropped": job.delta_buffer_dropped,
        "output_bytes": job.output_bytes,
        "completion_tokens": job.completion_tokens,
        "tokens_source": job.tokens_source,
        "partial_output_discarded": partial_discarded,
        "queue_depth_at_admission": job.queue_depth_at_admission,
        "queue_wait_ms": job.queue_wait_ms(),
        "ttft_gateway_ms": job.ttft_ms(),
        "service_ms": job.service_ms(),
        "e2e_gateway_ms": job.e2e_ms(),
        "decode_tokens_per_s": job.decode_tokens_per_s(),
    }
