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


def test_secure_m2_profile_requires_auth_credentials_and_tls():
    cfg = load_config(ROOT / "configs" / "m2_secure.toml")
    assert cfg.security.enabled is True
    assert cfg.security.require_tls is True
    assert cfg.security.users_file == Path("secrets/users.toml")
    assert cfg.gateway.tls_certfile == Path("artifacts/tls/gateway.crt")
    assert cfg.router.enabled is True
    assert cfg.domains["redes"].default_model != cfg.domains["prontuario"].default_model
    assert set(cfg.domains["redes"].models) == set(cfg.domains["prontuario"].models)


def test_replica_profile_has_two_equivalent_nodes_for_same_model():
    cfg = load_config(ROOT / "configs" / "m2_replicas.toml")
    replicas = [node for node in cfg.nodes if node.model == "qwen3-1.7b"]
    assert [node.name for node in replicas] == ["redes-1", "redes-2"]
    assert len({(node.threads, node.ctx_size, node.max_inflight) for node in replicas}) == 1


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


def test_llama_node_requires_http_url():
    raw = sim_config_dict()
    raw["nodes"][0] = {"name": "x", "kind": "llama_server", "model": "sim-small", "url": "ftp://x"}
    with pytest.raises(ValidationError, match="url http"):
        build(raw)


def test_https_backend_requires_runtime_certificate_and_key():
    raw = sim_config_dict()
    raw["nodes"][0] = {
        "name": "redes-1",
        "kind": "llama_server",
        "model": "sim-small",
        "url": "https://localhost:8101",
    }
    with pytest.raises(ValidationError, match="nó https exige"):
        build(raw)
