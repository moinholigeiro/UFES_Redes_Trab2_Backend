"""Políticas de ordem de preferência entre nós elegíveis para o mesmo domínio.

A ordem é calculada e a admissão ocorre no mesmo passo síncrono, então a
escolha usa o estado atual das filas (pendentes + ativos) sem corrida.
"""

from __future__ import annotations

from .scheduler import NodeScheduler


class Balancer:
    def __init__(self, policy: str) -> None:
        if policy not in {"round_robin", "least_loaded", "least_latency"}:
            raise ValueError(f"política de balanceamento desconhecida: {policy!r}")
        self.policy = policy
        self._cursor: dict[str, int] = {}

    def order(self, domain: str, candidates: list[NodeScheduler]) -> list[NodeScheduler]:
        if not candidates:
            return []
        if self.policy == "round_robin":
            start = self._cursor.get(domain, 0) % len(candidates)
            self._cursor[domain] = start + 1
            return candidates[start:] + candidates[:start]
        if self.policy == "least_loaded":
            return sorted(candidates, key=lambda s: (s.in_system, s.name))
        # least_latency: nós sem observação primeiro (warm-up); depois menor EWMA de serviço.
        return sorted(
            candidates,
            key=lambda s: (
                s.stats.observations > 0,
                s.stats.service_ewma_s or 0.0,
                s.name,
            ),
        )
