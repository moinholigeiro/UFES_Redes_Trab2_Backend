"""Testes do escalonador por nó com backend simulado (sem HTTP)."""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from pathlib import Path

import pytest

from llm_gateway.backends.simulated import SimulatedBackend
from llm_gateway.config import NodeConfig, SimulationConfig
from llm_gateway.jobs import Job, JobState
from llm_gateway.metrics import RequestLog
from llm_gateway.scheduler import NodeScheduler, Overloaded


def make_job(max_out: int = 10, deadline_s: float = 60.0, maxsize: int = 256) -> Job:
    now = time.monotonic()
    return Job(
        request_id=uuid.uuid4().hex,
        domain="redes",
        prompt="redes-v1",
        prompt_hash="0" * 16,
        output="text",
        schema=None,
        messages=[{"role": "user", "content": "oi"}],
        sampling={"temperature": 0.7},
        max_output_tokens=max_out,
        input_chars=2,
        events=asyncio.Queue(maxsize=maxsize),
        enqueued_at=now,
        deadline=now + deadline_s,
    )


def make_sched(
    tmp_path: Path,
    *,
    max_inflight: int = 1,
    max_queue: int = 4,
    tps: float = 200.0,
    response: str = "uma duas tres quatro cinco",
    fail_after: int | None = None,
    queue_timeout_s: float = 60.0,
    stall_s: float = 5.0,
) -> tuple[NodeScheduler, RequestLog]:
    sim = SimulationConfig(tokens_per_second=tps, response=response, fail_after_deltas=fail_after)
    node = NodeConfig(
        name="n1",
        kind="simulated",
        model="m",
        max_inflight=max_inflight,
        max_queue=max_queue,
        simulation=sim,
    )
    log = RequestLog(tmp_path / "log.jsonl")
    sched = NodeScheduler(
        node,
        SimulatedBackend(sim),
        stall_timeout_s=stall_s,
        queue_timeout_s=queue_timeout_s,
        log=log,
    )
    return sched, log


async def drain(job: Job) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    while True:
        event, data = await asyncio.wait_for(job.events.get(), timeout=10)
        events.append((event, data))
        if event in ("done", "error"):
            return events


def read_log(log: RequestLog, path: Path) -> list[dict]:
    log.close()
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


async def test_concurrency_limit_is_respected_and_dispatch_is_fifo(tmp_path):
    sched, log = make_sched(tmp_path, max_inflight=2, max_queue=10, tps=100.0, response="a b c d e")
    jobs = [make_job() for _ in range(6)]
    for job in jobs:
        sched.admit(job)
    max_active = 0

    async def sample():
        nonlocal max_active
        while True:
            max_active = max(max_active, sched.active_count)
            await asyncio.sleep(0.002)

    sampler = asyncio.create_task(sample())
    sched.start()
    try:
        results = await asyncio.gather(*(drain(j) for j in jobs))
    finally:
        sampler.cancel()
        await sched.stop()

    assert max_active == 2
    assert all(r[-1][0] == "done" for r in results)
    assert all(j.state is JobState.DONE for j in jobs)
    by_dispatch = sorted(jobs, key=lambda j: j.dispatched_at)
    assert by_dispatch == jobs
    assert sched.active_count == 0 and sched.pending_count == 0
    records = read_log(log, tmp_path / "log.jsonl")
    assert len(records) == 6
    assert all(r["status"] == "done" and r["tokens_source"] == "unknown" for r in records)
    assert all(r["completion_tokens"] is None for r in records)


async def test_admission_rejects_when_capacity_is_full(tmp_path):
    sched, log = make_sched(tmp_path, max_inflight=1, max_queue=1)
    first, second, third = make_job(), make_job(), make_job()
    sched.admit(first)
    sched.admit(second)
    with pytest.raises(Overloaded):
        sched.admit(third)
    assert sched.stats.rejected == 1
    assert third.state is JobState.QUEUED and third.node == ""
    await sched.stop()
    log.close()


async def test_cancel_queued_job_removes_it_without_touching_active(tmp_path):
    sched, log = make_sched(tmp_path, max_inflight=1, max_queue=4, tps=50.0, response="a b c d")
    running, queued = make_job(), make_job()
    sched.admit(running)
    sched.admit(queued)
    sched.start()
    try:
        await asyncio.sleep(0.05)
        sched.cancel(queued, "client_disconnected")
        assert queued.state is JobState.CANCELLED
        assert sched.pending_count == 0
        events = await drain(running)
    finally:
        await sched.stop()

    assert events[-1][0] == "done"
    assert running.state is JobState.DONE
    cancelled = [r for r in read_log(log, tmp_path / "log.jsonl") if r["status"] == "cancelled"]
    assert len(cancelled) == 1
    assert cancelled[0]["cancel_reason"] == "client_disconnected"
    assert cancelled[0]["service_ms"] is None
    assert cancelled[0]["queue_wait_ms"] is None


async def test_cancel_active_job_releases_slot_for_next(tmp_path):
    sched, log = make_sched(tmp_path, max_inflight=1, max_queue=4, tps=5.0, response="a " * 40)
    long_job, next_job = make_job(), make_job()
    sched.admit(long_job)
    sched.admit(next_job)
    sched.start()
    try:
        first_event = await asyncio.wait_for(long_job.events.get(), timeout=5)
        assert first_event[0] == "delta"
        sched.cancel(long_job, "client_disconnected")
        events = await drain(next_job)
        assert events[-1][0] == "done"
        assert sched.active_count == 0
    finally:
        await sched.stop()

    assert long_job.state is JobState.CANCELLED
    assert long_job.delta_count >= 1
    records = {r["request_id"]: r for r in read_log(log, tmp_path / "log.jsonl")}
    assert records[long_job.request_id]["status"] == "cancelled"
    assert records[long_job.request_id]["partial_output_discarded"] is True
    assert records[next_job.request_id]["status"] == "done"


async def test_pending_job_expires_after_queue_timeout(tmp_path):
    sched, _log = make_sched(
        tmp_path, max_inflight=1, max_queue=4, tps=5.0, response="a " * 60, queue_timeout_s=0.3
    )
    blocker, waiting = make_job(), make_job()
    sched.admit(blocker)
    sched.admit(waiting)
    sched.start()
    try:
        events = await drain(waiting)
        assert [name for name, _ in events] == ["error"]
        assert events[0][1]["code"] == "queue_timeout"
        assert events[0][1]["partial"] is False
        assert waiting.state is JobState.EXPIRED
        sched.cancel(blocker, "test_cleanup")
    finally:
        await sched.stop()


async def test_pending_job_expires_at_total_deadline_before_queue_timeout(tmp_path):
    sched, _log = make_sched(tmp_path, max_inflight=1, max_queue=4, tps=1.0, queue_timeout_s=60.0)
    blocker, waiting = make_job(), make_job(deadline_s=0.2)
    sched.admit(blocker)
    sched.admit(waiting)
    sched.start()
    try:
        events = await drain(waiting)
        assert events[-1][0] == "error"
        assert events[-1][1]["code"] == "deadline_exceeded"
        assert waiting.state is JobState.EXPIRED
        assert waiting not in sched._pending
    finally:
        sched.cancel(blocker, "test_cleanup")
        await sched.stop()


async def test_queue_timeout_is_not_replaced_by_long_total_deadline(tmp_path):
    sched, _log = make_sched(
        tmp_path, max_inflight=1, max_queue=2, tps=10.0, response="a " * 100, queue_timeout_s=0.1
    )
    blocker, waiting = make_job(), make_job(deadline_s=30.0)
    sched.admit(blocker)
    sched.admit(waiting)
    sched.start()
    try:
        await drain(waiting)
    finally:
        sched.cancel(blocker, "test_cleanup")
        await sched.stop()


async def test_deadline_is_enforced_and_reports_partial_output(tmp_path):
    sched, _log = make_sched(tmp_path, max_inflight=1, max_queue=2, tps=20.0, response="a " * 100)
    job = make_job(deadline_s=0.3)
    sched.admit(job)
    sched.start()
    try:
        events = await drain(job)
    finally:
        await sched.stop()
    assert events[-1][0] == "error"
    assert events[-1][1]["code"] == "deadline_exceeded"
    assert events[-1][1]["partial"] is True
    assert job.state is JobState.FAILED


async def test_failure_mid_stream_emits_partial_error_without_done(tmp_path):
    sched, _log = make_sched(tmp_path, response="um dois tres quatro", fail_after=2)
    job = make_job()
    sched.admit(job)
    sched.start()
    try:
        events = await drain(job)
    finally:
        await sched.stop()
    names = [e for e, _ in events]
    assert names == ["delta", "delta", "error"]
    assert events[-1][1] == {
        "code": "backend_unavailable",
        "message": "falha simulada do nó",
        "partial": True,
        "retryable": True,
    }


async def test_failure_before_first_delta_is_not_partial(tmp_path):
    sched, _log = make_sched(tmp_path, response="um dois", fail_after=0)
    job = make_job()
    sched.admit(job)
    sched.start()
    try:
        events = await drain(job)
    finally:
        await sched.stop()
    assert events == [
        (
            "error",
            {
                "code": "backend_unavailable",
                "message": "falha simulada do nó",
                "partial": False,
                "retryable": True,
            },
        )
    ]
    assert job.ttft_ms() is None


async def test_slow_client_is_cut_off_instead_of_buffering_forever(tmp_path):
    sched, _log = make_sched(tmp_path, response="a " * 50, tps=500.0, stall_s=0.1)
    job = make_job(maxsize=2)
    sched.admit(job)
    sched.start()
    try:
        await asyncio.sleep(0.6)
        assert job.state is JobState.FAILED
        assert job.error_code == "client_too_slow"
        events = []
        while not job.events.empty():
            events.append(job.events.get_nowait())
        assert events[-1][0] == "error"
        assert events[-1][1]["code"] == "client_too_slow"
    finally:
        await sched.stop()
