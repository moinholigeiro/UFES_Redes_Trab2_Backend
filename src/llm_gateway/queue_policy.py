"""Políticas de ordem da fila de cada nó (pergunta-desafio da spec).

A fila guarda os pedidos que esperam uma vaga no nó. A política decide **qual pedido sai primeiro**
quando uma vaga abre e, por consequência, a posição que cada cliente vê no evento `queued`.

- `fifo`: ordem de chegada. Justa, simples e previsível.
- `short_first`: pedidos com menor `max_output_tokens` primeiro (o tamanho máximo da resposta é a
  única estimativa do tempo de serviço disponível antes de gerar). Para que um pedido longo não espere
  para sempre atrás de uma sequência de curtos, quem espera há mais de `aging_s` segundos é promovido
  para a frente, em ordem de chegada (envelhecimento, ou *aging*).

As duas funções são puras: recebem a fila e o relógio e devolvem a ordem. Isso facilita testar e
explicar, e o scheduler continua sendo o único dono da fila.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Literal

from .jobs import Job

PolicyName = Literal["fifo", "short_first"]


def _arrival(job: Job) -> float:
    return job.attempt_enqueued_at or job.enqueued_at


class QueuePolicy:
    def __init__(self, name: PolicyName = "fifo", aging_s: float = 30.0) -> None:
        if name not in ("fifo", "short_first"):
            raise ValueError(f"política de fila desconhecida: {name!r}")
        if aging_s <= 0:
            raise ValueError("aging_s deve ser positivo")
        self.name = name
        self.aging_s = aging_s

    def ordered(self, pending: Iterable[Job], now: float) -> list[Job]:
        """Devolve os pedidos na ordem em que serão atendidos."""
        jobs = list(pending)
        if self.name == "fifo":
            return jobs  # a deque já está em ordem de chegada

        def key(job: Job) -> tuple[int, float, float]:
            arrival = _arrival(job)
            if now - arrival >= self.aging_s:
                return (0, arrival, arrival)  # envelhecido: vai para a frente, por ordem de chegada
            return (1, float(job.max_output_tokens), arrival)

        return sorted(jobs, key=key)

    def next_job(self, pending: Iterable[Job], now: float) -> Job | None:
        order = self.ordered(pending, now)
        return order[0] if order else None
