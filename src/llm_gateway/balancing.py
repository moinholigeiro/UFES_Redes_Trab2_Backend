"""Políticas de ordem de preferência entre nós elegíveis para o mesmo domínio.

A ordem é calculada e a admissão ocorre no mesmo passo síncrono, então a
escolha usa o estado atual das filas (pendentes + ativos) sem corrida.
"""

from __future__ import annotations

from .scheduler import NodeScheduler

# least_latency reexamina o nó mais esquecido a cada N decisões.
EXPLORE_EVERY = 20


class Balancer:
    def __init__(self, policy: str) -> None:
        if policy not in {"round_robin", "least_loaded", "least_latency"}:
            raise ValueError(f"política de balanceamento desconhecida: {policy!r}")
        self.policy = policy
        self._cursor: dict[str, int] = {}
        # least_latency: quantas decisões já foram tomadas e quando cada nó foi o primeiro da lista.
        self._decisions: dict[str, int] = {}
        self._last_first: dict[str, int] = {}

    def order(self, domain: str, candidates: list[NodeScheduler]) -> list[NodeScheduler]:
        if not candidates:
            return []
        if self.policy == "round_robin":
            start = self._cursor.get(domain, 0) % len(candidates)
            self._cursor[domain] = start + 1
            return candidates[start:] + candidates[:start]
        if self.policy == "least_loaded":
            return sorted(candidates, key=lambda s: (s.in_system, s.name))
        return self._least_latency(domain, candidates)

    def _least_latency(self, domain: str, candidates: list[NodeScheduler]) -> list[NodeScheduler]:
        """Menor espera prevista = (pedidos no nó + 1) * EWMA do tempo de serviço do nó.

        - Nó ainda sem medição vem primeiro (aquecimento), para ganhar uma estimativa.
        - Multiplicar pela fila evita mandar tudo para o nó "rápido" até ele lotar.
        - A cada EXPLORE_EVERY decisões, o nó há mais tempo sem ser o primeiro passa à frente
          uma vez. Sem isso, um nó que foi lento uma vez nunca mais seria medido.
        """
        tick = self._decisions.get(domain, 0) + 1
        self._decisions[domain] = tick

        def expected_wait(s: NodeScheduler) -> tuple[bool, float, str]:
            ewma = s.stats.service_ewma_s
            if s.stats.observations == 0 or ewma is None:
                return (False, 0.0, s.name)
            return (True, (s.in_system + 1) * ewma, s.name)

        order = sorted(candidates, key=expected_wait)
        if tick % EXPLORE_EVERY == 0 and len(order) > 1:
            stalest = min(order, key=lambda s: (self._last_first.get(s.name, 0), s.name))
            order.remove(stalest)
            order.insert(0, stalest)
        self._last_first[order[0].name] = tick
        return order
