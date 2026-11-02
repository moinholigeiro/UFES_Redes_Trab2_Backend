"""Contrato entre o escalonador e um backend de inferência."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from ..jobs import Job


@dataclass(frozen=True)
class Delta:
    """Trecho de texto recebido do backend. Não é necessariamente um token."""

    text: str


@dataclass(frozen=True)
class Finish:
    reason: str
    usage: dict[str, Any] | None = None


Chunk = Delta | Finish


class Backend(Protocol):
    def stream(self, job: Job) -> AsyncIterator[Chunk]:
        """Produz deltas e, ao fim, exatamente um Finish. Levanta JobError em falha."""
        ...
