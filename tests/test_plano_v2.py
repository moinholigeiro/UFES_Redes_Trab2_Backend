"""Testes das mudanças do plano v2 (docs/PLANO.md): política de fila, posição na fila, migração da
fila de um nó que caiu, "menor latência" corrigida, vazão agregada e frontend servido pelo gateway."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

import httpx

from llm_gateway.balancing import EXPLORE_EVERY, Balancer
from llm_gateway.config import load_config
from llm_gateway.gateway import Gateway
from llm_gateway.metrics import NodeStats, RequestLog
from llm_gateway.queue_policy import QueuePolicy

from .conftest import build, sim_config_dict
from .test_balancing import replica
from .test_scheduler import drain, make_job, make_sched

ROOT = Path(__file__).resolve().parent.parent


# --- política de fila -----------------------------------------------------------------------------


def test_fifo_keeps_arrival_order():
    a, b, c = make_job(max_out=500), make_job(max_out=10), make_job(max_out=100)
    assert QueuePolicy("fifo").ordered([a, b, c], time.monotonic()) == [a, b, c]


def test_short_first_orders_by_max_output_tokens():
    a, b, c = make_job(max_out=500), make_job(max_out=10), make_job(max_out=100)
    assert QueuePolicy("short_first").ordered([a, b, c], time.monotonic()) == [b, c, a]


def test_short_first_aging_promotes_long_waiting_request():
    old_long, new_short = make_job(max_out=500), make_job(max_out=10)
    now = time.monotonic()
    old_long.enqueued_at = now - 31.0  # esperou mais que aging_s=30
    order = QueuePolicy("short_first", aging_s=30.0).ordered([new_short, old_long], now)
    assert order == [old_long, new_short]


# --- posição na fila (evento queued) --------------------------------------------------------------


async def test_queued_events_report_position_and_its_decrease(tmp_path):
    sched, _ = make_sched(tmp_path, max_inflight=1, max_queue=4, tps=50.0, response="a b c d e")
    first, second, third = make_job(), make_job(), make_job()
    for job in (first, second, third):
        sched.admit(job)
    sched.start()
    try:
        events = await drain(third, keep_queued=True)
    finally:
        await sched.stop()
    positions = [data["position"] for name, data in events if name == "queued"]
    assert positions[0] == 3  # entrou atrás de dois
    assert positions == sorted(positions, reverse=True)  # só diminui
    assert positions[-1] == 1
    assert events[-1][0] == "done"


async def test_short_first_policy_serves_short_request_before_long(tmp_path):
    sched, _ = make_sched(tmp_path, max_inflight=1, max_queue=4, tps=100.0, response="a b c")
    sched.policy = QueuePolicy("short_first")
    blocker, long_job, short_job = make_job(max_out=10), make_job(max_out=500), make_job(max_out=5)
    sched.admit(blocker)
    sched.admit(long_job)
    sched.admit(short_job)
    sched.start()
    try:
        await drain(long_job)
    finally:
        await sched.stop()
    assert short_job.dispatched_at is not None and long_job.dispatched_at is not None
    assert short_job.dispatched_at < long_job.dispatched_at


# --- migração da fila de um nó que caiu ------------------------------------------------------------


def _two_replicas_gateway(tmp_path: Path) -> Gateway:
    raw = sim_config_dict(
        nodes=[
            {
                "name": f"r{i}",
                "kind": "simulated",
                "model": "sim-small",
                "max_inflight": 1,
                "max_queue": 4,
                "simulation": {"tokens_per_second": 100.0, "response": "a b"},
            }
            for i in (1, 2)
        ]
        + [
            {
                "name": "pront",
                "kind": "simulated",
                "model": "sim-big",
                "simulation": {"tokens_per_second": 100.0, "response": "{}"},
            }
        ]
    )
    config = build(raw)
    from llm_gateway.backends import make_backend

    backends = {n.name: make_backend(n, None) for n in config.nodes}  # simulados não usam HTTP
    return Gateway(config, backends, RequestLog(tmp_path / "log.jsonl"))


async def test_pending_requests_migrate_when_node_goes_down(tmp_path):
    gateway = _two_replicas_gateway(tmp_path)
    r1, r2 = gateway.nodes["r1"], gateway.nodes["r2"]
    jobs = [make_job() for _ in range(3)]
    for job in jobs:
        job.model = "sim-small"
        r1.admit(job)
    assert r1.pending_count == 3
    r1.set_health(False, "backend_unavailable")  # o callback do gateway migra a fila
    assert r1.pending_count == 0
    assert r2.pending_count == 3
    assert all(job.attempt_nodes == ["r1", "r2"] for job in jobs)


async def test_pending_requests_stay_if_no_other_replica_is_healthy(tmp_path):
    gateway = _two_replicas_gateway(tmp_path)
    r1, r2 = gateway.nodes["r1"], gateway.nodes["r2"]
    r2.set_health(False, "health_check_failed")
    job = make_job()
    job.model = "sim-small"
    r1.admit(job)
    r1.set_health(False, "backend_unavailable")
    assert r1.pending_count == 1  # espera o nó voltar ou o queue_timeout


# --- menor latência --------------------------------------------------------------------------------


def test_least_latency_accounts_for_queue_length():
    fast_busy, slow_idle = replica("fast", max_queue=8), replica("slow", max_queue=8)
    fast_busy.stats.observe_service(1.0)
    slow_idle.stats.observe_service(2.5)
    for _ in range(3):  # 3 pedidos no rápido: espera prevista 4 * 1,0 = 4,0 s
        fast_busy.admit(make_job())
    # ocioso: espera prevista 1 * 2,5 = 2,5 s
    assert [n.name for n in Balancer("least_latency").order("d", [fast_busy, slow_idle])] == [
        "slow",
        "fast",
    ]


def test_least_latency_periodically_retries_forgotten_node():
    fast, slow = replica("fast"), replica("slow")
    fast.stats.observe_service(0.5)
    slow.stats.observe_service(5.0)
    balancer = Balancer("least_latency")
    firsts = [balancer.order("d", [fast, slow])[0].name for _ in range(EXPLORE_EVERY)]
    assert firsts[:-1] == ["fast"] * (EXPLORE_EVERY - 1)
    assert firsts[-1] == "slow"  # reamostragem do nó esquecido


# --- vazão agregada --------------------------------------------------------------------------------


def test_throughput_counts_requests_and_tokens_in_window():
    stats = NodeStats(started_at=0.0)
    for t in (10.0, 20.0, 30.0):
        stats.observe_completion(50, now=t)
    result = stats.throughput(now=60.0)
    assert result["window_s"] == 60.0
    assert result["requests_per_s"] == round(3 / 60.0, 4)
    assert result["tokens_per_s"] == round(150 / 60.0, 3)
    # em t=85 a janela começa em 25: só o pedido de t=30 continua contando
    assert stats.throughput(now=85.0)["requests_per_s"] == round(1 / 60.0, 4)


# --- frontend servido pelo gateway -----------------------------------------------------------------


def test_gateway_serves_frontend_when_configured(serve, tmp_path):
    front = tmp_path / "front"
    (front / "src").mkdir(parents=True)
    (front / "index.html").write_text("<!doctype html><title>t2</title>", encoding="utf-8")
    (front / "src" / "main.js").write_text("console.log('ok')", encoding="utf-8")
    raw = sim_config_dict()
    raw["gateway"]["frontend_dir"] = str(front)
    server = serve(raw)
    index = httpx.get(f"{server.url}/", timeout=5)
    script = httpx.get(f"{server.url}/src/main.js", timeout=5)
    assert index.status_code == 200 and "t2" in index.text
    assert script.status_code == 200 and "ok" in script.text


def test_experiment_profile_loads_with_long_timeouts():
    cfg = load_config(ROOT / "configs" / "experiment_simulated.toml")
    assert cfg.gateway.queue_timeout_s >= 900
    assert cfg.scheduling.policy == "fifo"


async def test_metrics_snapshot_exposes_throughput(tmp_path):
    gateway = _two_replicas_gateway(tmp_path)
    snapshot = gateway.snapshot()
    assert set(snapshot["throughput"]) == {"requests_per_s", "tokens_per_s"}
    assert snapshot["queue_policy"] == "fifo"
    await asyncio.sleep(0)


# --- resposta de texto cortada no limite de tokens ------------------------------------------------


async def test_text_answer_cut_at_token_limit_ends_with_done_length(tmp_path):
    sched, _ = make_sched(tmp_path, response="um dois tres quatro cinco seis")
    job = make_job(max_out=3)
    sched.admit(job)
    sched.start()
    try:
        events = await drain(job)
    finally:
        await sched.stop()
    assert [name for name, _ in events] == ["delta", "delta", "delta", "done"]
    assert events[-1][1]["finish_reason"] == "length"


# --- vaga presa: cancelado antes de a tarefa começar ----------------------------------------------


async def test_cancel_before_task_starts_releases_the_slot(tmp_path):
    """Regressão (09/11): o cliente desconecta no mesmo instante em que o pedido ganha a vaga.

    `task.cancel()` antes do primeiro passo descarta a corrotina sem rodar o finally de `_run`.
    Antes da correção, a vaga ficava ocupada para sempre e a fila parava.
    """
    sched, _ = make_sched(tmp_path, max_inflight=1, max_queue=4)
    stuck, next_job = make_job(), make_job()
    sched.admit(stuck)
    sched.admit(next_job)
    sched._pending.remove(stuck)
    sched._start(stuck)  # ganha a vaga e cria a tarefa...
    sched.cancel(stuck, "client_disconnected")  # ...e é cancelado antes de a tarefa rodar
    await asyncio.sleep(0.05)
    assert sched.active_count == 0
    assert stuck.finished
    sched.start()
    try:
        events = await drain(next_job)  # a fila volta a andar
    finally:
        await sched.stop()
    assert events[-1][0] == "done"
