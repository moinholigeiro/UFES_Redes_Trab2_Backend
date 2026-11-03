"""Contrato do protocolo cliente ↔ gateway: requisição e eventos SSE.

Eventos:
  meta   -> request_id, domínio, modelo, nó, prompt/schema e fila (antes de qualquer token)
  delta  -> {seq, text}: trecho gerado, encaminhado assim que chega do backend
  result -> {schema, data}: só para domínios de extração, após validação do JSON completo
  done   -> {finish_reason, completion_tokens, tokens_source}
  error  -> {code, message, partial, retryable}

Comentários SSE (`: keepalive`) são heartbeats e não são tokens.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

TERMINAL_EVENTS = frozenset({"done", "error"})


class GenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    domain: str = Field(min_length=1, max_length=64)
    input: str = Field(min_length=1)
    max_output_tokens: int | None = Field(default=None, ge=1, strict=True)


def sse_encode(event: str, data: dict[str, Any]) -> str:
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event}\ndata: {payload}\n\n"


def sse_comment(text: str) -> str:
    return f": {text}\n\n"


def iter_sse(lines: Iterable[str]) -> Iterator[tuple[str, dict[str, Any]]]:
    """Lê eventos SSE completos. Evento sem linha em branco final não é emitido."""
    event = "message"
    data_lines: list[str] = []
    for line in lines:
        if line == "":
            if data_lines:
                yield event, json.loads("\n".join(data_lines))
            event, data_lines = "message", []
        elif line.startswith(":"):
            continue
        elif line.startswith("event:"):
            event = line[len("event:") :].strip()
        elif line.startswith("data:"):
            data_lines.append(line[len("data:") :].removeprefix(" "))
