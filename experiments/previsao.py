"""Previsão do experimento obrigatório, feita ANTES de medir (a spec exige).

Modelo de fila em laço fechado com N clientes e um nó com K vagas:

- calibração (uma execução com N = K): T0 = TTFT médio sem fila; S = tempo médio de um pedido
  (do envio ao `done`) com o nó cheio;
- vazão máxima X = K / S pedidos por segundo;
- lei de Little: tempo de resposta R = N / X = N·S/K;
- quem espera na fila espera R − S; logo, para N > K:  TTFT ≈ (N/K − 1)·S + T0;
- para N ≤ K não há fila: TTFT ≈ T0;
- tokens/s agregados ≈ min(N, K) · (tokens médios por pedido) / S: crescem até N = K e ficam planos.

O "joelho" (onde o TTFT dispara) é N* = K. O arquivo gerado (previsao.json) deve ser commitado
antes das medições, para que a comparação previsão × medição não possa ser ajustada depois.

Uso:  python experiments/previsao.py --calibracao resultados/calibracao-k1.csv --k 1 \
          --clientes 1,2,4,8,16 --saida resultados/previsao-k1.json
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import UTC, datetime
from pathlib import Path


def calibrar(caminho: Path) -> dict[str, float]:
    with caminho.open(encoding="utf-8") as fh:
        linhas = [linha for linha in csv.DictReader(fh) if linha["status"] == "ok"]
    if not linhas:
        raise SystemExit(f"calibração sem pedidos concluídos: {caminho}")
    ttfts = [float(linha["ttft_ms"]) for linha in linhas if linha["ttft_ms"]]
    e2es = [float(linha["e2e_ms"]) for linha in linhas]
    tokens = [int(linha["tokens"]) for linha in linhas if linha["tokens"]]
    return {
        "T0_s": sum(ttfts) / len(ttfts) / 1000.0,
        "S_s": sum(e2es) / len(e2es) / 1000.0,
        "tokens_por_pedido": (sum(tokens) / len(tokens)) if tokens else 0.0,
        "pedidos_calibracao": len(linhas),
    }


def prever(calibracao: dict[str, float], k: int, clientes: list[int]) -> list[dict[str, float]]:
    t0, s, tok = calibracao["T0_s"], calibracao["S_s"], calibracao["tokens_por_pedido"]
    pontos = []
    for n in clientes:
        ttft = t0 if n <= k else (n / k - 1.0) * s + t0
        pontos.append(
            {
                "clientes": n,
                "ttft_previsto_s": round(ttft, 3),
                "tokens_por_s_previsto": round(min(n, k) * tok / s, 3) if s > 0 else 0.0,
                "pedidos_por_s_previsto": round(min(n, k) / s, 4) if s > 0 else 0.0,
            }
        )
    return pontos


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--calibracao", type=Path, required=True)
    p.add_argument("--k", type=int, required=True, help="vagas por nó (max_inflight = slots do llama-server)")
    p.add_argument("--clientes", default="1,2,4,8,16")
    p.add_argument("--saida", type=Path, required=True)
    args = p.parse_args(argv)
    calib = calibrar(args.calibracao)
    clientes = [int(x) for x in args.clientes.split(",")]
    documento = {
        "gerado_em": datetime.now(UTC).isoformat(timespec="seconds"),
        "modelo": "laço fechado + lei de Little: TTFT = (N/K - 1)*S + T0 para N > K",
        "k": args.k,
        "joelho_previsto_N": args.k,
        "calibracao": {chave: round(valor, 4) for chave, valor in calib.items()},
        "pontos": prever(calib, args.k, clientes),
    }
    args.saida.parent.mkdir(parents=True, exist_ok=True)
    args.saida.write_text(json.dumps(documento, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(documento, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
