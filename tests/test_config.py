from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from llm_gateway.config import load_config

from .conftest import build, sim_config_dict

ROOT = Path(__file__).resolve().parent.parent


def test_repository_config_loads():
    cfg = load_config(ROOT / "configs" / "cpu_minimal.toml")
    assert set(cfg.domains) == {"redes", "prontuario"}
    assert cfg.domains["redes"].models != cfg.domains["prontuario"].models
    assert all(n.kind == "llama_server" for n in cfg.nodes)
    assert all(n.url.startswith("http://127.0.0.1") for n in cfg.nodes)


def test_secure_m2_profile_requires_auth_credentials_and_tls():
    cfg = load_config(ROOT / "configs" / "m2_secure.toml")
    assert cfg.security.enabled is True
    assert cfg.security.require_tls is True
    assert cfg.security.users_file == Path("secrets/users.toml")
    assert cfg.gateway.tls_certfile == Path("artifacts/tls/gateway.crt")
    assert cfg.router.enabled is False  # roteador opcional (decisão D3)
    assert cfg.domains["redes"].default_model != cfg.domains["prontuario"].default_model
    assert set(cfg.domains["redes"].models) == set(cfg.domains["prontuario"].models)
    assert cfg.gateway.backend_ca_file == Path("secrets/llm-nodes-ca.pem")
    assert all(node.url.startswith("https://") for node in cfg.nodes)

    raw = load_config(ROOT / "configs" / "m2_secure.toml").model_dump(
        mode="json", by_alias=True, exclude_none=True
    )
    raw["gateway"].pop("backend_ca_file")
    with pytest.raises(ValidationError, match="backend_ca_file"):
        build(raw)


def test_replica_profile_has_two_equivalent_nodes_for_same_model():
    cfg = load_config(ROOT / "configs" / "m2_replicas.toml")
    replicas = [node for node in cfg.nodes if node.model == "qwen3-1.7b"]
    assert [node.name for node in replicas] == ["redes-1", "redes-2"]
    assert len({(node.model, node.max_inflight, node.max_queue) for node in replicas}) == 1


def test_tls_pair_and_security_requirements_are_validated():
    raw = sim_config_dict()
    raw["gateway"]["tls_certfile"] = "cert.crt"
    with pytest.raises(ValidationError, match="devem ser informados juntos"):
        build(raw)

    raw = sim_config_dict()
    raw["security"] = {"enabled": True, "require_tls": True, "users_file": "users.toml"}
    with pytest.raises(ValidationError, match="tls_certfile"):
        build(raw)


def test_simulated_config_is_valid_only_with_flag():
    raw = sim_config_dict()
    build(raw)
    raw["gateway"]["allow_simulated_backends"] = False
    with pytest.raises(ValidationError, match="allow_simulated_backends"):
        build(raw)


def test_unknown_model_reference_is_rejected():
    raw = sim_config_dict()
    raw["nodes"][0]["model"] = "inexistente"
    with pytest.raises(ValidationError, match="modelo não declarado"):
        build(raw)


def test_domain_without_eligible_node_is_rejected():
    raw = sim_config_dict()
    raw["nodes"] = [n for n in raw["nodes"] if n["model"] != "sim-big"]
    with pytest.raises(ValidationError, match="não tem nó para o modelo"):
        build(raw)


def test_unknown_prompt_is_rejected():
    raw = sim_config_dict()
    raw["domains"]["redes"]["prompt"] = "nao-existe"
    with pytest.raises(ValidationError, match="prompt desconhecido"):
        build(raw)


def test_json_domain_requires_known_schema():
    raw = sim_config_dict()
    del raw["domains"]["prontuario"]["schema"]
    with pytest.raises(ValidationError, match="schema conhecido"):
        build(raw)


def test_text_domain_rejects_schema():
    raw = sim_config_dict()
    raw["domains"]["redes"]["schema"] = "prontuario-v1"
    with pytest.raises(ValidationError, match="schema só é permitido"):
        build(raw)


def test_limits_must_be_positive_and_consistent():
    raw = sim_config_dict()
    raw["nodes"][0]["max_inflight"] = 0
    with pytest.raises(ValidationError):
        build(raw)

    raw = sim_config_dict()
    raw["domains"]["redes"]["max_output_tokens"] = 99999
    with pytest.raises(ValidationError, match="max_output_tokens_limit"):
        build(raw)


def test_default_above_domain_limit_is_rejected():
    raw = sim_config_dict()
    raw["domains"]["redes"]["default_max_output_tokens"] = 300
    raw["domains"]["redes"]["max_output_tokens"] = 200
    with pytest.raises(ValidationError, match="default_max_output_tokens"):
        build(raw)


def test_unknown_keys_are_rejected():
    raw = sim_config_dict()
    raw["gateway"]["porta_magica"] = 1
    with pytest.raises(ValidationError):
        build(raw)


@pytest.mark.parametrize(
    "origin",
    [
        "*",
        "http://backend.example",
        "https://frontend.example/path",
        "https://user@frontend.example",
        "https://frontend.example:99999",
        "https://frontend.example/",
    ],
)
def test_config_rejects_unsafe_cors_origins(origin):
    raw = sim_config_dict(gateway={"cors_origins": [origin]})
    with pytest.raises(ValidationError):
        build(raw)


@pytest.mark.parametrize("timeout", [float("inf"), float("nan")])
def test_gateway_timeouts_must_be_finite(timeout):
    raw = sim_config_dict(gateway={"request_deadline_s": timeout})
    with pytest.raises(ValidationError):
        build(raw)


def test_health_check_timeout_cannot_exceed_probe_interval():
    raw = sim_config_dict(gateway={"health_check_timeout_s": 3, "health_check_interval_s": 2})
    with pytest.raises(ValidationError):
        build(raw)


def test_body_timeout_cannot_exceed_total_deadline():
    with pytest.raises(ValidationError):
        build(sim_config_dict(gateway={"request_body_timeout_s": 3, "request_deadline_s": 2}))


def test_auth_header_limit_has_finite_bounds():
    for limit in (127, 65_537):
        with pytest.raises(ValidationError):
            build(sim_config_dict(gateway={"max_auth_header_bytes": limit}))


def test_event_buffer_must_reserve_result_and_done_slots():
    raw = sim_config_dict(gateway={"event_buffer_size": 1})
    with pytest.raises(ValidationError):
        build(raw)


def test_event_buffer_has_a_finite_upper_bound():
    with pytest.raises(ValidationError):
        build(sim_config_dict(gateway={"event_buffer_size": 65_537}))


@pytest.mark.parametrize("url", ["http://user@node:8101", "https://node:99999", "http://node/path"])
def test_node_url_rejects_credentials_invalid_port_and_path(url):
    raw = sim_config_dict()
    raw["nodes"][0] = {"name": "node", "kind": "llama_server", "url": url, "model": "sim-small"}
    with pytest.raises(ValidationError):
        build(raw)


def test_remote_llm_node_requires_https():
    raw = sim_config_dict()
    raw["nodes"][0] = {
        "name": "remote",
        "kind": "llama_server",
        "model": "sim-small",
        "url": "http://node.example:8101",
    }
    with pytest.raises(ValidationError, match="loopback"):
        build(raw)


def test_real_llm_nodes_start_unhealthy_until_probe_succeeds():
    from llm_gateway.backends.simulated import SimulatedBackend
    from llm_gateway.metrics import RequestLog
    from llm_gateway.scheduler import NodeScheduler

    node = build(
        {
            **sim_config_dict(),
            "nodes": [
                {
                    "name": "remote",
                    "kind": "llama_server",
                    "url": "http://127.0.0.1:8101",
                    "model": "sim-small",
                },
                sim_config_dict()["nodes"][1],
            ],
        }
    ).nodes[0]
    scheduler = NodeScheduler(node, object(), stall_timeout_s=1, queue_timeout_s=1, log=RequestLog(None))
    assert scheduler.healthy is False

    simulated_node = build(sim_config_dict()).nodes[0]
    simulated = SimulatedBackend(simulated_node.simulation)
    sim_scheduler = NodeScheduler(
        simulated_node, simulated, stall_timeout_s=1, queue_timeout_s=1, log=RequestLog(None)
    )
    assert sim_scheduler.healthy is True


def test_llama_node_requires_http_url():
    raw = sim_config_dict()
    raw["nodes"][0] = {"name": "x", "kind": "llama_server", "model": "sim-small", "url": "ftp://x"}
    with pytest.raises(ValidationError, match="url http"):
        build(raw)


def test_https_backend_does_not_require_private_node_certificate_in_gateway():
    raw = sim_config_dict()
    raw["nodes"][0] = {
        "name": "redes-1",
        "kind": "llama_server",
        "model": "sim-small",
        "url": "https://localhost:8101",
    }
    raw["gateway"]["backend_ca_file"] = "ca.pem"
    assert build(raw).nodes[0].url == "https://localhost:8101"


def test_remote_http_node_is_allowed_with_api_key(tmp_path: Path):
    key = tmp_path / "chave"
    key.write_text("segredo-de-teste\n", encoding="utf-8")
    raw = sim_config_dict()
    raw["nodes"][0] = {
        "name": "remote",
        "kind": "llama_server",
        "model": "sim-small",
        "url": "http://10.0.0.5:8101",
        "api_key_file": str(key),
    }
    cfg = build(raw)
    assert cfg.nodes[0].api_key_file == key
