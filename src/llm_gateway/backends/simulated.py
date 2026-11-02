"""Backend simulado. Usado apenas em testes (exige gateway.allow_simulated_backends=true).

Não substitui medições com LLM real: serve para testar SSE, filas, cancelamento e falhas.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from ..config import SimulationConfig
from ..jobs import JobError
from .base import Chunk, Delta, Finish

if TYPE_CHECKING:
    from ..jobs import Job


class SimulatedBackend:
    def __init__(self, simulation: SimulationConfig) -> None:
        self._sim = simulation
        self._pieces = re.findall(r"\S+\s*", simulation.response) or [simulation.response]

    async def stream(self, job: Job) -> AsyncIterator[Chunk]:
        if self._sim.startup_delay_s:
            await asyncio.sleep(self._sim.startup_delay_s)
        interval = 1.0 / self._sim.tokens_per_second
        for index, piece in enumerate(self._pieces):
            if self._sim.fail_after_deltas is not None and index == self._sim.fail_after_deltas:
                raise JobError("backend_unavailable", "falha simulada do nó")
            await asyncio.sleep(interval)
            yield Delta(piece)
        yield Finish("stop", None)
