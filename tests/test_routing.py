"""Intelligence increment: grouped TF-IDF routing and conservative fallbacks."""

from __future__ import annotations

from pathlib import Path

import httpx

from llm_gateway.config import load_config
from llm_gateway.protocol import iter_sse
from llm_gateway.routing import RouteUncertain, SemanticRouter, load_examples

from .conftest import sim_config_dict

ROOT = Path(__file__).resolve().parents[1]


def router_for_profile() -> SemanticRouter:
    config = load_config(ROOT / "configs" / "m2_secure.toml")
    return SemanticRouter(config.router.examples_file, config.domains, config.router)


def test_training_set_is_synthetic_balanced_and_groups_do_not_leak():
    examples = load_examples(ROOT / "data/routing_examples.jsonl", {"redes", "prontuario"})
    assert len(examples) == 120
    assert all(item["group"] for item in examples)
    router = router_for_profile()
    train_groups = {router.examples[i]["group"] for i in router.train_indices}
    test_groups = {router.examples[i]["group"] for i in router.test_indices}
    assert train_groups.isdisjoint(test_groups)
    assert len(router.train_indices) + len(router.test_indices) == 120


def test_router_reports_holdout_accuracy_and_confusion_matrices():
    report = router_for_profile().evaluation()
    assert report["examples"] == 120
    assert report["train_examples"] + report["test_examples"] == 120
    assert report["seed"] == 42
    assert report["domain_accuracy"] >= 0.8
    assert report["complexity_accuracy"] >= 0.8
    assert report["domain_confusion_matrix"] == [
        [report["test_examples"] // 2, 0],
        [0, report["test_examples"] // 2],
    ]


def test_auto_routes_domain_and_selects_small_or_large_model():
    router = router_for_profile()
    simple_network = "O que significa TCP? Responda de modo direto para a disciplina de Redes."
    decision = router.route("auto", simple_network)
    assert decision.domain == "redes"
    assert decision.domain_confidence >= 0.6
    assert decision.complexity == "simple"
    assert decision.model == "qwen3-1.7b"

    complex_network = (
        "Analise um cenário de rede que use controle de congestionamento. Compare alternativas, "
        "explique trade-offs de latência e vazão e proponha como medir o resultado."
    )
    hard = router.route("auto", complex_network)
    assert hard.domain == "redes"
    assert hard.complexity == "complex"
    assert hard.model == "qwen35-4b"

    simple_clinical = (
        "Extraia dose de medicamento deste prontuário sintético: "
        "metformina 850 mg via oral duas vezes ao dia."
    )
    medical = router.route("auto", simple_clinical)
    assert medical.domain == "prontuario"
    assert medical.model == "qwen3-1.7b"


def test_low_domain_confidence_requests_explicit_domain():
    router = router_for_profile()
    try:
        router.route("auto", "Qual é a cor do céu?")
    except RouteUncertain as exc:
        assert len(exc.candidates) == 2
        assert sum(score for _, score in exc.candidates) > 0.99
    else:
        raise AssertionError("texto fora dos domínios não deveria ser roteado ao acaso")


def test_explicit_domain_is_not_overridden_by_semantic_classifier():
    router = router_for_profile()
    decision = router.route("redes", "Extraia a dose do medicamento no prontuário.")
    assert decision.domain == "redes"
    assert decision.requested_domain == "redes"


def auto_api_config(*, router_enabled: bool = True) -> dict:
    raw = sim_config_dict(
        nodes=[
            {
                "name": "small-node",
                "kind": "simulated",
                "model": "sim-small",
                "max_inflight": 1,
                "max_queue": 4,
                "simulation": {"tokens_per_second": 200, "response": "small model"},
            },
            {
                "name": "large-node",
                "kind": "simulated",
                "model": "sim-big",
                "max_inflight": 1,
                "max_queue": 4,
                "simulation": {"tokens_per_second": 200, "response": "large model"},
            },
        ],
    )
    for name in ("redes", "prontuario"):
        raw["domains"][name]["models"] = ["sim-small", "sim-big"]
        raw["domains"][name]["default_model"] = "sim-small" if name == "redes" else "sim-big"
        raw["domains"][name]["model_by_complexity"] = {"simple": "sim-small", "complex": "sim-big"}
    raw["router"] = {
        "enabled": router_enabled,
        "examples_file": str(ROOT / "data/routing_examples.jsonl"),
        "confidence_threshold": 0.6,
        "complexity_confidence_threshold": 0.55,
        "test_fraction": 0.25,
        "random_seed": 42,
    }
    return raw


def test_api_auto_routes_and_reports_decision_in_meta(serve):
    server = serve(auto_api_config())
    text = "O que significa TCP? Responda de modo direto para a disciplina de Redes."
    with httpx.stream(
        "POST",
        f"{server.url}/v1/generate",
        json={"domain": "auto", "input": text},
        headers={"Accept": "text/event-stream"},
        timeout=10,
    ) as response:
        events = list(iter_sse(response.iter_lines()))
    meta = events[0][1]
    assert events[0][0] == "meta"
    assert meta["requested_domain"] == "auto"
    assert meta["domain"] == "redes"
    assert meta["model"] == "sim-small"
    assert meta["complexity"] == "simple"
    assert meta["route_confidence"] >= 0.6
    assert "".join(data["text"] for name, data in events if name == "delta") == "small model"


def test_explicit_domain_uses_configured_default_model_not_complexity_router(serve):
    server = serve(auto_api_config())
    text = "O que significa TCP? Responda de modo direto para a disciplina de Redes."
    with httpx.stream(
        "POST",
        f"{server.url}/v1/generate",
        json={"domain": "redes", "input": text},
        headers={"Accept": "text/event-stream"},
        timeout=10,
    ) as response:
        events = list(iter_sse(response.iter_lines()))
    meta = events[0][1]
    assert meta["domain"] == "redes"
    assert meta["model"] == "sim-small"
    assert meta["complexity"] is None
    assert "".join(data["text"] for name, data in events if name == "delta") == "small model"


def test_api_uncertain_domain_returns_422_and_auto_disabled_is_explicit(serve):
    server = serve(auto_api_config())
    uncertain = httpx.post(
        f"{server.url}/v1/generate", json={"domain": "auto", "input": "Qual é a cor do céu?"}
    )
    assert uncertain.status_code == 422
    assert uncertain.json()["error"]["code"] == "domain_uncertain"
    assert len(uncertain.json()["error"]["candidates"]) == 2

    disabled = serve(auto_api_config(router_enabled=False))
    response = httpx.post(f"{disabled.url}/v1/generate", json={"domain": "auto", "input": "TCP"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "router_disabled"
