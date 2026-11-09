"""Testes das ferramentas do experimento (experiments/): previsão, carga em laço fechado e agregação.

Um erro aqui invalidaria a medição real no laboratório sem nenhum aviso, por isso elas têm testes
como o resto do código.
"""

from __future__ import annotations

import asyncio
import csv
import importlib.util
import sys
from pathlib import Path

import pytest

from .conftest import sim_config_dict

EXPERIMENTS = Path(__file__).resolve().parent.parent / "experiments"


def _modulo(nome: str):
    spec = importlib.util.spec_from_file_location(f"experimento_{nome}", EXPERIMENTS / f"{nome}.py")
    assert spec and spec.loader
    modulo = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = modulo
    spec.loader.exec_module(modulo)
    return modulo


previsao = _modulo("previsao")
carga = _modulo("carga")
graficos = _modulo("graficos")


def test_prediction_is_flat_until_k_then_linear():
    calib = {"T0_s": 0.5, "S_s": 10.0, "tokens_por_pedido": 100.0}
    pontos = {p["clientes"]: p for p in previsao.prever(calib, k=2, clientes=[1, 2, 4, 8])}
    assert pontos[1]["ttft_previsto_s"] == 0.5
    assert pontos[2]["ttft_previsto_s"] == 0.5
    assert pontos[4]["ttft_previsto_s"] == pytest.approx((4 / 2 - 1) * 10 + 0.5)
    assert pontos[8]["ttft_previsto_s"] == pytest.approx((8 / 2 - 1) * 10 + 0.5)
    # vazão agregada para de crescer no joelho N* = K
    assert pontos[2]["tokens_por_s_previsto"] == pontos[8]["tokens_por_s_previsto"] == 20.0


def test_closed_loop_load_marks_transient_and_reaches_target(serve):
    raw = sim_config_dict(
        nodes=[
            {
                "name": "redes-1",
                "kind": "simulated",
                "model": "sim-small",
                "max_inflight": 1,
                "max_queue": 16,
                "simulation": {"tokens_per_second": 200.0, "response": "a " * 20, "report_usage": True},
            },
            {
                "name": "prontuario-1",
                "kind": "simulated",
                "model": "sim-big",
                "simulation": {"tokens_per_second": 200.0, "response": "{}"},
            },
        ]
    )
    server = serve(raw)
    amostras, duracao = asyncio.run(
        carga.rodar(
            url=server.url, token=None, ca=None, clientes=3, pedidos=4, dominio="redes",
            perguntas=["pergunta"], tokens_curto=4, tokens_longo=8, fracao_curtos=0.0,
            aquecimento=False, semente=1,
        )
    )
    transientes = [a for a in amostras if a.transiente]
    estaveis = [a for a in amostras if a.status == "ok" and not a.transiente]
    assert len(transientes) == 3  # padrão: descarta N = 3
    assert len(estaveis) == 4
    assert all(a.tokens == 8 and a.finish_reason == "length" for a in estaveis)
    assert all(a.primeira_posicao is not None for a in estaveis)
    assert duracao > 0


def test_aggregation_ignores_transient_rows_and_computes_ci(tmp_path: Path):
    colunas = ["clientes", "duracao_s", "k", "politica", "rep", "status", "ttft_ms", "tokens", "classe",
               "transiente"]
    for rep, ttfts in ((1, [1000, 3000]), (2, [2000, 4000])):
        with (tmp_path / f"k1-fifo-n2-r{rep}.csv").open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=colunas)
            w.writeheader()
            base = {"clientes": 2, "duracao_s": 10, "k": 1, "politica": "fifo", "rep": rep, "status": "ok",
                    "tokens": 50, "classe": "unica"}
            w.writerow({**base, "ttft_ms": 99999, "transiente": True})
            for t in ttfts:
                w.writerow({**base, "ttft_ms": t, "transiente": False})
    resumo = graficos.agregar(graficos.carregar(tmp_path))
    ponto = resumo[("1", "fifo", 2)]
    assert ponto["repeticoes"] == 2
    assert ponto["ttft_s"] == pytest.approx(2.5)  # média das médias (2,0 e 3,0); o transiente ficou de fora
    assert ponto["tokens_por_s"] == pytest.approx(10.0)  # 100 tokens em 10 s
