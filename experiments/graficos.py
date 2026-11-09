"""Gráficos e tabela-resumo a partir dos CSVs do gerador de carga.

Lê todos os `*.csv` de uma pasta de resultados (cada um é uma execução, com as colunas extras
`clientes`, `k`, `politica`, `rep` e `duracao_s`) e gera:

1. ttft_vs_clientes.png — TTFT médio por N (média das repetições, com intervalo de confiança de 95%),
   o p95, e a curva prevista (previsao-k*.json) por cima;
2. vazao_vs_clientes.png — tokens/s agregados por N;
3. desafio_ttft_por_classe.png — box plot do TTFT dos pedidos curtos e longos em cada política
   (só se houver execuções com `fracao_curtos`);
4. resumo.md — a tabela com os números de cada ponto.

Uso:  python experiments/graficos.py --resultados experiments/resultados/2026-11-10
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path

# t de Student bicaudal 95% para poucos graus de liberdade (sem depender do scipy)
T95 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262,
       10: 2.228, 15: 2.131, 20: 2.086, 30: 2.042}


def t95(graus: int) -> float:
    if graus <= 0:
        return float("nan")
    chaves = sorted(k for k in T95 if k <= graus)
    return T95[chaves[-1]] if graus <= 30 else 1.96


def media_ic(valores: list[float]) -> tuple[float, float]:
    """Média e meia-largura do IC 95% (entre repetições)."""
    if not valores:
        return float("nan"), float("nan")
    media = statistics.fmean(valores)
    if len(valores) < 2:
        return media, float("nan")
    return media, t95(len(valores) - 1) * statistics.stdev(valores) / math.sqrt(len(valores))


def percentil(valores: list[float], q: float) -> float:
    ordenados = sorted(valores)
    return ordenados[min(len(ordenados) - 1, int(q * len(ordenados)))] if ordenados else float("nan")


def carregar(pasta: Path) -> list[dict[str, str]]:
    linhas: list[dict[str, str]] = []
    for arquivo in sorted(pasta.glob("*.csv")):
        if arquivo.name.startswith("calibracao"):
            continue
        with arquivo.open(encoding="utf-8") as fh:
            for linha in csv.DictReader(fh):
                linha["_arquivo"] = arquivo.name
                linhas.append(linha)
    return linhas


def agregar(linhas: list[dict[str, str]]) -> dict[tuple[str, str, int], dict[str, float]]:
    """Por (k, política, N): TTFT e vazão com média e IC entre repetições."""
    por_execucao: dict[tuple[str, str, int, str], list[dict[str, str]]] = defaultdict(list)
    for linha in linhas:
        k, politica = linha.get("k", "?"), linha.get("politica", "fifo")
        chave = (k, politica, int(linha["clientes"]), linha["_arquivo"])
        por_execucao[chave].append(linha)
    pontos: dict[tuple[str, str, int], dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for (k, politica, n, _), execucao in por_execucao.items():
        ok = [x for x in execucao if x["status"] == "ok" and x["ttft_ms"]]
        if not ok:
            continue
        duracao = float(execucao[0]["duracao_s"])
        tokens = sum(int(x["tokens"]) for x in ok if x["tokens"])
        ponto = pontos[(k, politica, n)]
        ponto["ttft_rep"].append(statistics.fmean(float(x["ttft_ms"]) / 1000 for x in ok))
        ponto["ttft_todos"].extend(float(x["ttft_ms"]) / 1000 for x in ok)
        ponto["tps_rep"].append(tokens / duracao if duracao > 0 else float("nan"))
        ponto["erros"].append(float(sum(1 for x in execucao if x["status"] != "ok")))
    resumo: dict[tuple[str, str, int], dict[str, float]] = {}
    for chave, ponto in pontos.items():
        ttft, ttft_ic = media_ic(ponto["ttft_rep"])
        tps, tps_ic = media_ic(ponto["tps_rep"])
        resumo[chave] = {
            "repeticoes": len(ponto["ttft_rep"]),
            "ttft_s": ttft, "ttft_ic95": ttft_ic, "ttft_p95_s": percentil(ponto["ttft_todos"], 0.95),
            "tokens_por_s": tps, "tokens_por_s_ic95": tps_ic, "erros": sum(ponto["erros"]),
        }
    return resumo


def previsoes(pasta: Path) -> dict[str, dict]:
    saida = {}
    for arquivo in pasta.glob("previsao-k*.json"):
        documento = json.loads(arquivo.read_text(encoding="utf-8"))
        saida[str(documento["k"])] = documento
    return saida


def escrever_resumo(pasta: Path, resumo: dict, prev: dict[str, dict]) -> Path:
    linhas = [
        "| K | política | N | repetições | TTFT médio (s) ± IC95 | TTFT previsto (s) | TTFT p95 (s) "
        "| tokens/s agregados ± IC95 | erros |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for (k, politica, n), r in sorted(resumo.items(), key=lambda item: (item[0][0], item[0][1], item[0][2])):
        previsto = "—"
        if k in prev:
            for ponto in prev[k]["pontos"]:
                if ponto["clientes"] == n:
                    previsto = f"{ponto['ttft_previsto_s']:.2f}"
        linhas.append(
            f"| {k} | {politica} | {n} | {r['repeticoes']} | {r['ttft_s']:.2f} ± {r['ttft_ic95']:.2f} | "
            f"{previsto} | {r['ttft_p95_s']:.2f} | {r['tokens_por_s']:.2f} ± {r['tokens_por_s_ic95']:.2f} | "
            f"{int(r['erros'])} |"
        )
    destino = pasta / "resumo.md"
    destino.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return destino


def desenhar(pasta: Path, linhas: list[dict[str, str]], resumo: dict, prev: dict[str, dict]) -> list[Path]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    gerados: list[Path] = []
    series = sorted({(k, pol) for (k, pol, _) in resumo})
    fig, ax = plt.subplots(figsize=(7, 4.5))
    for k, politica in series:
        pts = sorted((n, r) for (kk, pp, n), r in resumo.items() if (kk, pp) == (k, politica))
        ns = [n for n, _ in pts]
        ax.errorbar(ns, [r["ttft_s"] for _, r in pts], yerr=[r["ttft_ic95"] for _, r in pts],
                    marker="o", capsize=3, label=f"medido K={k} ({politica})")
        ax.plot(ns, [r["ttft_p95_s"] for _, r in pts], linestyle=":", marker="x", label=f"p95 K={k}")
        if k in prev:
            pp = prev[k]["pontos"]
            ax.plot([p["clientes"] for p in pp], [p["ttft_previsto_s"] for p in pp], linestyle="--",
                    label=f"previsto K={k}")
            ax.axvline(prev[k]["joelho_previsto_N"], color="gray", linewidth=0.6)
    ax.set_xscale("log", base=2)
    ax.set_xlabel("clientes simultâneos (N)")
    ax.set_ylabel("TTFT (s)")
    ax.set_title("TTFT × N — medido (média ± IC95) e previsto")
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=8)
    destino = pasta / "ttft_vs_clientes.png"
    fig.tight_layout()
    fig.savefig(destino, dpi=150)
    plt.close(fig)
    gerados.append(destino)

    fig, ax = plt.subplots(figsize=(7, 4.5))
    for k, politica in series:
        pts = sorted((n, r) for (kk, pp, n), r in resumo.items() if (kk, pp) == (k, politica))
        ax.errorbar([n for n, _ in pts], [r["tokens_por_s"] for _, r in pts],
                    yerr=[r["tokens_por_s_ic95"] for _, r in pts], marker="o", capsize=3,
                    label=f"medido K={k} ({politica})")
        if k in prev:
            pp = prev[k]["pontos"]
            ax.plot([p["clientes"] for p in pp], [p["tokens_por_s_previsto"] for p in pp], linestyle="--",
                    label=f"previsto K={k}")
    ax.set_xscale("log", base=2)
    ax.set_xlabel("clientes simultâneos (N)")
    ax.set_ylabel("tokens/s agregados")
    ax.set_title("Vazão agregada × N")
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=8)
    destino = pasta / "vazao_vs_clientes.png"
    fig.tight_layout()
    fig.savefig(destino, dpi=150)
    plt.close(fig)
    gerados.append(destino)

    mistas = [x for x in linhas if x["classe"] in {"curta", "longa"} and x["status"] == "ok" and x["ttft_ms"]]
    if mistas:
        grupos: dict[tuple[str, str], list[float]] = defaultdict(list)
        for x in mistas:
            grupos[(x.get("politica", "fifo"), x["classe"])].append(float(x["ttft_ms"]) / 1000)
        rotulos = sorted(grupos)
        fig, ax = plt.subplots(figsize=(7, 4.5))
        ax.boxplot([grupos[r] for r in rotulos], tick_labels=[f"{p}\n{c}" for p, c in rotulos])
        ax.set_ylabel("TTFT (s)")
        ax.set_title("Pergunta-desafio: TTFT por política de fila e tipo de pedido")
        ax.grid(True, axis="y", alpha=0.3)
        destino = pasta / "desafio_ttft_por_classe.png"
        fig.tight_layout()
        fig.savefig(destino, dpi=150)
        plt.close(fig)
        gerados.append(destino)
    return gerados


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--resultados", type=Path, required=True)
    args = p.parse_args(argv)
    linhas = carregar(args.resultados)
    if not linhas:
        raise SystemExit(f"nenhum CSV em {args.resultados}")
    resumo = agregar(linhas)
    prev = previsoes(args.resultados)
    print(f"resumo: {escrever_resumo(args.resultados, resumo, prev)}")
    try:
        for caminho in desenhar(args.resultados, linhas, resumo, prev):
            print(f"gráfico: {caminho}")
    except ImportError:
        print("matplotlib não instalado: pip install -e .[experiments] para gerar os gráficos")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
