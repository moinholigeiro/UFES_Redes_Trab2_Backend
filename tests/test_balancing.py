"""Políticas de balanceamento e admissão com fallback entre réplicas equivalentes."""

from __future__ import annotations

import asyncio
import time
import uuid

import httpx
import pytest

from llm_gateway.backends import make_backend
from llm_gateway.backends.simulated import SimulatedBackend
from llm_gateway.balancing import Balancer
from llm_gateway.config import NodeConfig, SimulationConfig
from llm_gateway.gateway import Gateway
from llm_gateway.jobs import Job
from llm_gateway.metrics import RequestLog
from llm_gateway.scheduler import NodeScheduler, Overloaded

from .conftest import build, sim_config_dict


def replica(name: str, max_queue: int = 2) -> NodeScheduler:
    sim = SimulationConfig(tokens_per_second=10.0, response="a")
    node = NodeConfig(
        name=name, kind="simulated", model="m", max_inflight=1, max_queue=max_queue, simulation=sim
    )
    return NodeScheduler(
        node, SimulatedBackend(sim), stall_timeout_s=5, queue_timeout_s=60, log=RequestLog(None)
    )


def job() -> Job:
    now = time.monotonic()
    return Job(
        request_id=uuid.uuid4().hex,
        domain="d",
        prompt="redes-v1",
        prompt_hash="0",
        output="text",
        schema=None,
        messages=[],
        sampling={},
        max_output_tokens=4,
        input_chars=1,
        events=asyncio.Queue(),
        enqueued_at=now,
        deadline=now + 30,
    )


def names(nodes: list[NodeScheduler]) -> list[str]:
    return [n.name for n in nodes]


def test_round_robin_rotates_starting_point_per_domain():
    a, b, c = replica("a"), replica("b"), replica("c")
    bal = Balancer("round_robin")
    assert names(bal.order("d", [a, b, c])) == ["a", "b", "c"]
    assert names(bal.order("d", [a, b, c])) == ["b", "c", "a"]
    assert names(bal.order("d", [a, b, c])) == ["c", "a", "b"]
    assert names(bal.order("outro", [a, b, c])) == ["a", "b", "c"]


def test_least_loaded_prefers_fewest_jobs_in_system():
    a, b = replica("a"), replica("b")
    a.admit(job())
    assert names(Balancer("least_loaded").order("d", [a, b])) == ["b", "a"]


def test_least_latency_warms_up_unobserved_nodes_then_uses_ewma():
    a, b = replica("a"), replica("b")
    bal = Balancer("least_latency")
    a.stats.observe_service(0.5)
    assert names(bal.order("d", [a, b])) == ["b", "a"]
    b.stats.observe_service(2.0)
    assert names(bal.order("d", [a, b])) == ["a", "b"]


def test_unknown_policy_is_rejected():
    with pytest.raises(ValueError):
        Balancer("aleatoria")


async def test_admission_falls_back_to_other_replica_when_first_is_full():
    raw = sim_config_dict(
        policy="round_robin",
        nodes=[
            {
                "name": "r1",
                "kind": "simulated",
                "model": "sim-small",
                "max_inflight": 1,
                "max_queue": 1,
                "simulation": {"tokens_per_second": 10.0, "response": "a"},
            },
            {
                "name": "r2",
                "kind": "simulated",
                "model": "sim-small",
                "max_inflight": 1,
                "max_queue": 1,
                "simulation": {"tokens_per_second": 10.0, "response": "a"},
            },
        ],
        domains={
            "redes": {
                "description": "x",
                "models": ["sim-small"],
                "prompt": "redes-v1",
                "output": "text",
                "default_max_output_tokens": 8,
                "max_output_tokens": 16,
            }
        },
    )
    config = build(raw)
    client = httpx.AsyncClient()
    backends = {n.name: make_backend(n, client) for n in config.nodes}
    gw = Gateway(config, backends, RequestLog(None))
    placed = []
    for _ in range(5):
        j = job()
        j.domain = "redes"
        try:
            placed.append(gw.admit(j).name)
        except Overloaded:
            placed.append("overloaded")
    await client.aclose()
    assert placed == ["r1", "r2", "r1", "r2", "overloaded"]
