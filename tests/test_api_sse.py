"""API HTTP com servidor real: SSE progressivo, admissão, heartbeat, cancelamento e falha mid-stream."""

from __future__ import annotations

import json
import time
from pathlib import Path

import httpx

from llm_gateway.protocol import iter_sse

from .conftest import VALID_PRONTUARIO, sim_config_dict


def collect_events(response: httpx.Response) -> tuple[list[tuple[str, dict]], list[tuple[float, str]]]:
    """Retorna eventos completos e o instante de cada linha recebida (para medir progressividade)."""
    stamps: list[tuple[float, str]] = []

    def lines():
        for line in response.iter_lines():
            stamps.append((time.monotonic(), line))
            yield line

    return list(iter_sse(lines())), stamps


def stream_post(base: str, body: dict, timeout: float = 30.0):
    return httpx.stream(
        "POST",
        f"{base}/v1/generate",
        json=body,
        headers={"Accept": "text/event-stream"},
        timeout=timeout,
    )


def test_health_domains_and_metrics_expose_no_prompts(serve):
    server = serve(sim_config_dict())
    with httpx.Client(base_url=server.url) as client:
        assert client.get("/health").json() == {"status": "ok"}
        domains = client.get("/v1/domains").json()["domains"]
        assert {d["name"] for d in domains} == {"redes", "prontuario"}
        blob = json.dumps(domains) + client.get("/metrics").text
        assert "Você é o assistente" not in blob
        assert "Regras:" not in blob
        metrics = client.get("/metrics").json()
        assert set(metrics["nodes"]) == {"redes-1", "prontuario-1"}


def test_text_stream_is_progressive_ordered_and_unicode_preserving(serve):
    response_text = "Ação, é, 日本 — " + " ".join(f"p{i}" for i in range(20))
    raw = sim_config_dict(
        nodes=[
            {
                "name": "redes-1",
                "kind": "simulated",
                "model": "sim-small",
                "max_inflight": 1,
                "max_queue": 2,
                "simulation": {"tokens_per_second": 10.0, "response": response_text},
            }
        ],
        domains={
            "redes": {
                "description": "x",
                "models": ["sim-small"],
                "prompt": "redes-v1",
                "output": "text",
                "default_max_output_tokens": 64,
                "max_output_tokens": 128,
            }
        },
    )
    server = serve(raw)
    with stream_post(server.url, {"domain": "redes", "input": "o que é TCP?"}) as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        events, stamps = collect_events(resp)

    names = [name for name, _ in events]
    assert names[0] == "meta" and names[-1] == "done"
    assert names.count("delta") >= 20
    assert "".join(d["text"] for name, d in events if name == "delta") == response_text
    assert [d["seq"] for name, d in events if name == "delta"] == list(range(1, names.count("delta") + 1))

    delta_times = [t for t, line in stamps if line.startswith("event: delta")]
    done_time = next(t for t, line in stamps if line.startswith("event: done"))
    assert done_time - delta_times[0] > 1.0, "primeiro delta deve chegar bem antes do fim"

    done = events[-1][1]
    assert done == {
        "finish_reason": "stop",
        "completion_tokens": None,
        "tokens_source": "unknown",
    }


def test_prontuario_emits_validated_result_before_done(serve):
    server = serve(sim_config_dict())
    with stream_post(server.url, {"domain": "prontuario", "input": "Paciente de 54 anos."}) as resp:
        assert resp.status_code == 200
        events, _ = collect_events(resp)

    names = [name for name, _ in events]
    assert names[0] == "meta"
    assert names[-2:] == ["result", "done"]
    meta = events[0][1]
    assert meta["schema"] == "prontuario-v1"
    assert meta["prompt_hash"] and "Regras" not in json.dumps(meta)
    result = events[-2][1]
    assert result["schema"] == "prontuario-v1"
    assert result["data"] == json.loads(VALID_PRONTUARIO)


def test_invalid_json_output_is_error_not_result(serve):
    raw = sim_config_dict()
    raw["nodes"][1]["simulation"]["response"] = '{"idade": 54, "sexo": "masculino"'
    server = serve(raw)
    with stream_post(server.url, {"domain": "prontuario", "input": "texto"}) as resp:
        events, _ = collect_events(resp)

    names = [name for name, _ in events]
    assert "result" not in names and "done" not in names
    assert events[-1][0] == "error"
    assert events[-1][1]["code"] == "schema_invalid"
    assert events[-1][1]["partial"] is True


def test_admission_errors_have_distinct_status_codes(serve):
    server = serve(sim_config_dict(gateway={"max_request_bytes": 2048, "max_input_chars": 50}))
    with httpx.Client(base_url=server.url, timeout=10) as client:
        r = client.post("/v1/generate", json={"domain": "inexistente", "input": "oi"})
        assert r.status_code == 400 and r.json()["error"]["code"] == "unknown_domain"

        r = client.post("/v1/generate", json={"domain": "redes", "input": "oi", "model": "x"})
        assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_request"

        r = client.post("/v1/generate", json={"domain": "redes", "input": ""})
        assert r.status_code == 422

        r = client.post("/v1/generate", json={"domain": "redes", "input": "a" * 51})
        assert r.status_code == 413 and r.json()["error"]["code"] == "input_too_large"

        r = client.post("/v1/generate", json={"domain": "redes", "input": "oi", "max_output_tokens": 9999})
        assert r.status_code == 422 and r.json()["error"]["code"] == "max_output_tokens_exceeds_limit"

        r = client.post("/v1/generate", content=b"x" * 4096, headers={"Content-Type": "application/json"})
        assert r.status_code == 413 and r.json()["error"]["code"] == "body_too_large"


def test_queue_full_returns_503_with_retry_after(serve):
    raw = sim_config_dict(
        nodes=[
            {
                "name": "redes-1",
                "kind": "simulated",
                "model": "sim-small",
                "max_inflight": 1,
                "max_queue": 1,
                "simulation": {"tokens_per_second": 2.0, "response": "a " * 60},
            }
        ],
        domains={
            "redes": {
                "description": "x",
                "models": ["sim-small"],
                "prompt": "redes-v1",
                "output": "text",
                "default_max_output_tokens": 64,
                "max_output_tokens": 128,
            }
        },
    )
    server = serve(raw)
    body = {"domain": "redes", "input": "oi"}
    with stream_post(server.url, body) as first, stream_post(server.url, body) as second:
        assert first.status_code == 200 and second.status_code == 200
        with httpx.Client(base_url=server.url, timeout=10) as client:
            r = client.post("/v1/generate", json=body)
        assert r.status_code == 503
        assert r.headers["retry-after"] == "1"
        assert r.json()["error"]["code"] == "queue_full"


def test_queued_request_receives_heartbeat_comments_not_tokens(serve):
    raw = sim_config_dict(
        gateway={"heartbeat_interval_s": 0.1},
        nodes=[
            {
                "name": "redes-1",
                "kind": "simulated",
                "model": "sim-small",
                "max_inflight": 1,
                "max_queue": 2,
                "simulation": {"tokens_per_second": 2.0, "response": "a " * 30},
            }
        ],
        domains={
            "redes": {
                "description": "x",
                "models": ["sim-small"],
                "prompt": "redes-v1",
                "output": "text",
                "default_max_output_tokens": 64,
                "max_output_tokens": 128,
            }
        },
    )
    server = serve(raw)
    body = {"domain": "redes", "input": "oi"}
    with stream_post(server.url, body) as first:
        assert first.status_code == 200
        with stream_post(server.url, body) as second:
            lines = []
            keepalives = 0
            for line in second.iter_lines():
                lines.append(line)
                if line == ": keepalive":
                    keepalives += 1
                if keepalives >= 3:
                    break
    assert not any(line.startswith("event: delta") for line in lines)


def test_client_disconnect_cancels_active_job_and_frees_slot(serve, tmp_path: Path):
    raw = sim_config_dict(
        nodes=[
            {
                "name": "redes-1",
                "kind": "simulated",
                "model": "sim-small",
                "max_inflight": 1,
                "max_queue": 2,
                "simulation": {"tokens_per_second": 2.0, "response": "a " * 200},
            }
        ],
        domains={
            "redes": {
                "description": "x",
                "models": ["sim-small"],
                "prompt": "redes-v1",
                "output": "text",
                "default_max_output_tokens": 64,
                "max_output_tokens": 128,
            }
        },
    )
    server = serve(raw)
    secret = "PRONTUARIO-SEGREDO-XYZ"
    body = {"domain": "redes", "input": secret}
    with stream_post(server.url, body) as resp:
        for line in resp.iter_lines():
            if line.startswith("event: delta"):
                break
    with httpx.Client(base_url=server.url, timeout=10) as client:
        deadline = time.monotonic() + 5
        while True:
            node = client.get("/metrics").json()["nodes"]["redes-1"]
            if node["active"] == 0:
                break
            assert time.monotonic() < deadline, "slot não foi liberado após desconexão"
            time.sleep(0.05)
        assert node["cancelled"] == 1

    records = [json.loads(x) for x in (tmp_path / "requests.jsonl").read_text().splitlines()]
    cancelled = [r for r in records if r["status"] == "cancelled"]
    assert cancelled and cancelled[0]["cancel_reason"] == "client_disconnected"
    assert cancelled[0]["partial_output_discarded"] is True
    assert secret not in json.dumps(records), "log não pode conter texto da entrada"


def test_mid_stream_failure_reports_partial_error_without_done(serve):
    raw = sim_config_dict()
    raw["nodes"][0]["simulation"]["response"] = "um dois tres quatro cinco"
    raw["nodes"][0]["simulation"]["fail_after_deltas"] = 2
    server = serve(raw)
    with stream_post(server.url, {"domain": "redes", "input": "oi"}) as resp:
        events, _ = collect_events(resp)
    assert [name for name, _ in events] == ["meta", "delta", "delta", "error"]
    error = events[-1][1]
    assert error["partial"] is True and error["retryable"] is True
    assert error["code"] == "backend_unavailable"


def test_failure_before_first_token_is_not_partial(serve):
    raw = sim_config_dict()
    raw["nodes"][0]["simulation"]["response"] = "um dois"
    raw["nodes"][0]["simulation"]["fail_after_deltas"] = 0
    server = serve(raw)
    with stream_post(server.url, {"domain": "redes", "input": "oi"}) as resp:
        events, _ = collect_events(resp)
    assert [name for name, _ in events] == ["meta", "error"]
    assert events[-1][1]["partial"] is False
