"""Registro de nós, domínios e admissão de requisições."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from .backends.base import Backend
from .balancing import Balancer
from .config import AppConfig
from .jobs import FAILOVER_CODES, Job
from .metrics import RequestLog
from .queue_policy import QueuePolicy
from .scheduler import NodeScheduler, Overloaded


class NoHealthyNodes(Exception):
    """Nenhum backend elegível está saudável no momento."""


class Gateway:
    def __init__(self, config: AppConfig, backends: dict[str, Backend], log: RequestLog) -> None:
        self.config = config
        self.log = log
        self.balancer = Balancer(config.balancing.policy)
        gw = config.gateway
        self.nodes: dict[str, NodeScheduler] = {
            n.name: NodeScheduler(
                n,
                backends[n.name],
                stall_timeout_s=gw.client_stall_timeout_s,
                queue_timeout_s=gw.queue_timeout_s,
                log=log,
                policy=QueuePolicy(config.scheduling.policy, config.scheduling.aging_s),
            )
            for n in config.nodes
        }
        for scheduler in self.nodes.values():
            scheduler.on_unhealthy = self.migrate_pending
        self.domain_nodes: dict[str, list[NodeScheduler]] = {
            dname: [self.nodes[n.name] for n in config.nodes if n.model in dom.models]
            for dname, dom in config.domains.items()
        }

    def start(self) -> None:
        for node in self.nodes.values():
            node.start()

    async def stop(self) -> None:
        await asyncio.gather(*(node.stop() for node in self.nodes.values()))
        self.log.close()

    def admit(self, job: Job) -> NodeScheduler:
        """Escolhe o nó pela política e admite o job. Levanta Overloaded se todos estiverem cheios."""
        domain_config = self.config.domains[job.domain]
        target_model = job.requested_model or domain_config.default_model or domain_config.models[0]
        candidates = [s for s in self.domain_nodes[job.domain] if s.healthy and s.node.model == target_model]
        if not candidates:
            raise NoHealthyNodes(job.domain)
        for sched in self.balancer.order(job.domain, candidates):
            try:
                sched.admit(job)
                return sched
            except Overloaded:
                continue
        raise Overloaded(job.domain)

    def retry_before_first_delta(self, job: Job) -> bool:
        """Reenfileira uma única vez em réplica compatível após falha sem delta.

        A chamada deve ocorrer depois que a task da tentativa anterior terminou,
        para que o slot e o log daquela tentativa já estejam liberados/gravados.
        """
        if (
            job.delta_count
            or job.error_code not in FAILOVER_CODES
            or job.finished_at is None
            or time.monotonic() >= job.deadline
            or job.attempt > self.config.balancing.max_failover_attempts
        ):
            return False
        attempted = set(job.attempt_nodes)
        candidates = [
            s
            for s in self.domain_nodes[job.domain]
            if s.healthy and s.name not in attempted and s.node.model == job.model
        ]
        for sched in self.balancer.order(job.domain, candidates):
            if time.monotonic() >= job.deadline:
                return False
            if sched.in_system >= sched.node.max_inflight + sched.node.max_queue:
                continue
            # Limpa os eventos da tentativa anterior ANTES de admitir: a admissão já publica
            # o `queued` da nova tentativa, que o cliente precisa receber.
            while not job.events.empty():
                job.events.get_nowait()
            try:
                sched.admit(job)
                job.error_code = None
                job.cancel_reason = None
                job.finish_reason = None
                job.finished_at = None
                job.dispatched_at = None
                job.first_delta_at = None
                job.last_delta_at = None
                job.completion_tokens = None
                job.tokens_source = None
                job.delta_count = 0
                job.output_chars = 0
                job.task = None
                return True
            except Overloaded:
                continue
        return False

    def migrate_pending(self, failed: NodeScheduler) -> int:
        """Leva para outra réplica os pedidos que esperavam na fila de um nó que caiu.

        Sem isso, eles ficariam parados até o nó voltar ou até estourar `queue_timeout_s`.
        Só migra para nó saudável com o mesmo modelo; se nenhum aceitar, o pedido continua
        na fila original e espera o nó voltar. Devolve quantos pedidos foram migrados.
        """
        moved = 0
        for job in failed.pending_jobs():
            candidates = [
                s
                for s in self.domain_nodes[job.domain]
                if s is not failed and s.healthy and s.node.model == job.model
            ]
            for target in self.balancer.order(job.domain, candidates):
                if target.in_system >= target.node.max_inflight + target.node.max_queue:
                    continue
                failed.remove_pending(job)
                target.admit(job)  # incrementa job.attempt; o cliente recebe um novo `meta`
                moved += 1
                break
        return moved

    def cancel(self, job: Job, reason: str) -> None:
        if job.node:
            self.nodes[job.node].cancel(job, reason)

    def snapshot(self) -> dict[str, Any]:
        nodes = {name: sched.snapshot() for name, sched in self.nodes.items()}
        return {
            "balancing_policy": self.balancer.policy,
            "queue_policy": self.config.scheduling.policy,
            "throughput": {
                "requests_per_s": round(sum(n["throughput"]["requests_per_s"] for n in nodes.values()), 4),
                "tokens_per_s": round(sum(n["throughput"]["tokens_per_s"] for n in nodes.values()), 3),
            },
            "domains": {
                name: {"nodes": [s.name for s in scheds]} for name, scheds in self.domain_nodes.items()
            },
            "nodes": nodes,
        }
