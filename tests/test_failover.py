"""Failover entre réplicas equivalentes: retry só antes do primeiro delta."""

from __future__ import annotations

import json

import httpx
import pytest

from llm_gateway.protocol import iter_sse

from .conftest import sim_config_dict


def replicas_config(*, first_fail_after: int | None = 0, max_failover_attempts: int = 1) -> dict:
    raw = sim_config_dict(
        nodes=[
            {
                "name": "redes-a",
                "kind": "simulated",
                "model": "sim-small",
                "max_inflight": 1,
                "max_queue": 2,
                "simulation": {
                    "tokens_per_second": 200,
                    "response": "falha nunca deve vazar",
                    "fail_after_deltas": first_fail_after,
                },
            },
            {
                "name": "redes-b",
                "kind": "simulated",
                "model": "sim-small",
                "max_inflight": 1,
                "max_queue": 2,
                "simulation": {
                    "tokens_per_second": 200,
                    "response": "réplica compatível respondeu com sucesso",
                },
            },
        ],
        domains={
            "redes": {
                "description": "assistente de redes",
                "models": ["sim-small"],
                "prompt": "redes-v1",
                "output": "text",
                "default_max_output_tokens": 64,
                "max_output_tokens": 128,
            }
        },
    )
    raw["balancing"]["max_failover_attempts"] = max_failover_attempts
    return raw


def post_stream(url: str):
    return httpx.stream(
        "POST",
        f"{url}/v1/generate",
        json={"domain": "redes", "input": "Explique o TCP."},
        headers={"Accept": "text/event-stream"},
        timeout=10,
    )


def test_failure_before_first_delta_retries_compatible_replica(serve, tmp_path):
    server = serve(replicas_config())
    with post_stream(server.url) as response:
        assert response.status_code == 200
        events = list(iter_sse(response.iter_lines()))

    names = [name for name, _ in events]
    assert names[0] == "meta" and names[-1] == "done"
    meta = events[0][1]
    assert meta["request_id"]
    assert meta["attempt"] == 2
    assert meta["attempt_nodes"] == ["redes-a", "redes-b"]
    assert meta["node"] == "redes-b"
    text = "".join(data["text"] for name, data in events if name == "delta")
    assert text == "réplica compatível respondeu com sucesso"
    assert "falha nunca" not in text

    attempts = [json.loads(line) for line in (tmp_path / "requests.jsonl").read_text().splitlines()]
    assert len(attempts) == 2
    assert [(row["node"], row["attempt"], row["status"]) for row in attempts] == [
        ("redes-a", 1, "failed"),
        ("redes-b", 2, "done"),
    ]


def test_mid_stream_failure_is_not_retried_or_concatenated(serve):
    server = serve(replicas_config(first_fail_after=1))
    with post_stream(server.url) as response:
        events = list(iter_sse(response.iter_lines()))

    assert [name for name, _ in events] == ["meta", "delta", "error"]
    assert events[0][1]["node"] == "redes-a"
    assert events[0][1]["attempt"] == 1
    assert events[-1][1]["partial"] is True
    assert events[-1][1]["retryable"] is True
    assert "done" not in [name for name, _ in events]


def test_no_healthy_nodes_is_removed_from_eligibility(serve):
    raw = replicas_config(first_fail_after=0)
    raw["nodes"] = raw["nodes"][:1]
    server = serve(raw)
    with post_stream(server.url) as response:
        events = list(iter_sse(response.iter_lines()))
    assert events[-1][0] == "error"
    assert events[-1][1]["partial"] is False

    response = httpx.post(
        f"{server.url}/v1/generate", json={"domain": "redes", "input": "segunda"}, timeout=5
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "no_healthy_nodes"
    assert response.headers["retry-after"] == "2"


def test_failover_can_be_disabled_by_config(serve):
    server = serve(replicas_config(max_failover_attempts=0))
    with post_stream(server.url) as response:
        events = list(iter_sse(response.iter_lines()))
    assert [name for name, _ in events] == ["meta", "error"]
    assert events[0][1]["node"] == "redes-a"
    assert events[0][1]["attempt"] == 1


def test_expired_request_is_not_retried_on_compatible_replica(serve):
    raw = replicas_config()
    raw["gateway"]["request_deadline_s"] = 0.01
    raw["gateway"]["request_body_timeout_s"] = 0.01
    raw["nodes"][0]["simulation"]["startup_delay_s"] = 0.05
    server = serve(raw)
    with post_stream(server.url) as response:
        events = list(iter_sse(response.iter_lines()))

    assert events[-1][0] == "error"
    assert events[-1][1]["code"] == "deadline_exceeded"
    assert events[0][1]["attempt"] == 1
    assert events[0][1]["attempt_nodes"] == ["redes-a"]


@pytest.mark.parametrize(
    "code", ["queue_timeout", "deadline_exceeded", "schema_invalid", "incomplete_stream"]
)
def test_non_transient_errors_are_not_eligible_for_automatic_failover(code):
    from llm_gateway.jobs import FAILOVER_CODES

    assert code not in FAILOVER_CODES
