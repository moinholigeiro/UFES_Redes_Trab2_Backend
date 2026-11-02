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
    with pytest.raises(ValidationError, match="não tem nó elegível"):
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
