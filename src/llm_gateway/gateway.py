"""Registro de nós, domínios e admissão de requisições."""

from __future__ import annotations

import asyncio
from typing import Any

from .backends.base import Backend
from .balancing import Balancer
from .config import AppConfig
from .jobs import Job
from .metrics import RequestLog
from .scheduler import NodeScheduler, Overloaded


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
            )
            for n in config.nodes
        }
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
        for sched in self.balancer.order(job.domain, self.domain_nodes[job.domain]):
            try:
                sched.admit(job)
                return sched
            except Overloaded:
                continue
        raise Overloaded(job.domain)

    def cancel(self, job: Job, reason: str) -> None:
        if job.node:
            self.nodes[job.node].cancel(job, reason)

    def snapshot(self) -> dict[str, Any]:
        return {
            "balancing_policy": self.balancer.policy,
            "domains": {
                name: {"nodes": [s.name for s in scheds]} for name, scheds in self.domain_nodes.items()
            },
            "nodes": {name: sched.snapshot() for name, sched in self.nodes.items()},
        }
