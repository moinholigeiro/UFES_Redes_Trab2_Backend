"""Gerador de carga em laço fechado para o experimento obrigatório e a pergunta-desafio.

Laço fechado: cada um dos N clientes manda um pedido, espera o evento terminal (`done` ou `error`)
e manda o próximo na hora, sem pausa. É o modelo da lei de Little usado na previsão
(experiments/previsao.py): com N clientes sempre ocupados, a fila do nó tem N − K pedidos esperando.

Regime estável: os N clientes começam juntos, e a primeira leva tem esperas de 0 a (N−1)·S,
diferentes das do regime estável (≈ (N/K − 1)·S). Por isso os primeiros `--descartar` pedidos
concluídos (padrão: N) são marcados `transiente=True` e não contam para a meta `--pedidos` nem
para os gráficos. Sem isso, com poucos pedidos por execução, só os que esperaram pouco chegam a
concluir, e o TTFT medido fica abaixo do real (viés achado no ensaio de 09/11).

Cada pedido vira uma linha no CSV, com os tempos medidos **no cliente**:
- ttft_ms: do envio do POST até o primeiro `delta` (inclui a espera na fila);
- e2e_ms: do envio até o evento terminal;
- tokens: `done.completion_tokens` (contagem do runtime). Sem contagem, fica vazio;
- primeira_posicao: a posição informada no primeiro `queued`.

Uso direto (o lab.py chama isto por você):
    python experiments/carga.py --url https://127.0.0.1:8443 --token-file .lab/token \
        --ca .lab/tls/ca.crt --clientes 4 --pedidos 30 --saida resultados/n4.csv
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import random
import ssl
import time
from dataclasses import asdict, dataclass, fields
from pathlib import Path

import httpx

AQUI = Path(__file__).resolve().parent


@dataclass
class Amostra:
    cliente: int
    seq: int
    classe: str  # "unica", "curta" ou "longa"
    max_tokens: int
    status: str  # "ok" ou "erro"
    erro: str
    finish_reason: str
    no: str
    tentativas: int
    primeira_posicao: int | None
    ttft_ms: float | None
    e2e_ms: float
    tokens: int | None
    trechos: int
    inicio_s: float  # instante do envio, relativo ao começo da medição
    transiente: bool = False  # primeira leva (fora do regime estável): não entra nos gráficos


def ler_perguntas(caminho: Path) -> list[str]:
    linhas = [linha.strip() for linha in caminho.read_text(encoding="utf-8").splitlines()]
    perguntas = [linha for linha in linhas if linha and not linha.startswith("#")]
    if not perguntas:
        raise SystemExit(f"nenhuma pergunta em {caminho}")
    return perguntas


async def um_pedido(
    client: httpx.AsyncClient, url: str, corpo: dict, t0: float
) -> tuple[str, str, str, str, int, int | None, float | None, float, int | None, int, float]:
    """Envia um pedido e lê o stream SSE até o evento terminal."""
    envio = time.perf_counter()
    primeiro_delta: float | None = None
    status, erro, finish, no, tentativas = "erro", "", "", "", 0
    posicao: int | None = None
    tokens: int | None = None
    trechos = 0
    try:
        async with client.stream("POST", f"{url}/v1/generate", json=corpo) as resp:
            if resp.status_code != 200:
                corpo_erro = (await resp.aread()).decode("utf-8", "replace")
                try:
                    erro = json.loads(corpo_erro)["error"]["code"]
                except (ValueError, KeyError, TypeError):
                    erro = f"http_{resp.status_code}"
            else:
                evento = "message"
                async for linha in resp.aiter_lines():
                    if linha.startswith("event:"):
                        evento = linha[6:].strip()
                        continue
                    if not linha.startswith("data:"):
                        continue
                    dados = json.loads(linha[5:].strip())
                    if evento == "meta":
                        no, tentativas = dados["node"], dados["attempt"]
                    elif evento == "queued" and posicao is None:
                        posicao = dados["position"]
                    elif evento == "delta":
                        trechos += 1
                        if primeiro_delta is None and dados["text"]:
                            primeiro_delta = time.perf_counter()
                    elif evento == "done":
                        status, finish = "ok", dados["finish_reason"]
                        tokens = dados.get("completion_tokens")
                        break
                    elif evento == "error":
                        erro = dados["code"]
                        break
    except httpx.HTTPError as exc:
        erro = type(exc).__name__
    fim = time.perf_counter()
    ttft = None if primeiro_delta is None else round((primeiro_delta - envio) * 1000, 3)
    e2e = round((fim - envio) * 1000, 3)
    return status, erro, finish, no, tentativas, posicao, ttft, e2e, tokens, trechos, round(envio - t0, 4)


async def rodar(
    *,
    url: str,
    token: str | None,
    ca: Path | None,
    clientes: int,
    pedidos: int,
    dominio: str,
    perguntas: list[str],
    tokens_curto: int,
    tokens_longo: int,
    fracao_curtos: float,
    aquecimento: bool,
    semente: int,
    descartar: int | None = None,
) -> tuple[list[Amostra], float]:
    """Roda N clientes até `pedidos` pedidos concluírem no regime estável. Devolve amostras e duração (s).

    A duração conta do fim do transitório (o `descartar`-ésimo pedido concluído) até o último pedido da meta,
    para que a vazão agregada também seja a do regime estável.
    """
    descartar = clientes if descartar is None else descartar
    rng = random.Random(semente)
    verify: bool | ssl.SSLContext = ssl.create_default_context(cafile=str(ca)) if ca else True
    headers = {"Accept": "text/event-stream"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    timeout = httpx.Timeout(connect=10.0, read=1800.0, write=30.0, pool=1800.0)
    limits = httpx.Limits(max_connections=clientes + 2, max_keepalive_connections=clientes + 2)
    amostras: list[Amostra] = []
    concluidos = 0
    transientes = 0
    inicio_estavel: float | None = None
    parar = asyncio.Event()
    duracao = 0.0

    def corpo_para(i: int) -> tuple[dict, str, int]:
        if fracao_curtos > 0:
            curta = rng.random() < fracao_curtos
            classe, maximo = ("curta", tokens_curto) if curta else ("longa", tokens_longo)
        else:
            classe, maximo = "unica", tokens_longo
        pergunta = perguntas[i % len(perguntas)]
        return {"domain": dominio, "input": pergunta, "max_output_tokens": maximo}, classe, maximo

    async with httpx.AsyncClient(verify=verify, headers=headers, timeout=timeout, limits=limits) as client:
        if aquecimento:  # carrega o modelo na memória; não entra na medição
            corpo, _, _ = corpo_para(0)
            await um_pedido(client, url, corpo, time.perf_counter())
        t0 = time.perf_counter()

        async def cliente(indice: int) -> None:
            nonlocal concluidos, transientes, inicio_estavel, duracao
            seq = 0
            while not parar.is_set():
                corpo, classe, maximo = corpo_para(indice * 1000 + seq)
                r = await um_pedido(client, url, corpo, t0)
                if parar.is_set():
                    return  # pedido terminou depois da meta: fora da medição
                status, erro, finish, no, tentativas, posicao, ttft, e2e, tokens, trechos, inicio = r
                transiente = status == "ok" and transientes < descartar
                amostras.append(
                    Amostra(indice, seq, classe, maximo, status, erro, finish, no, tentativas, posicao,
                            ttft, e2e, tokens, trechos, inicio, transiente)
                )
                seq += 1
                if transiente:
                    transientes += 1
                    if transientes == descartar:
                        inicio_estavel = time.perf_counter()
                elif status == "ok":
                    if inicio_estavel is None:  # descartar = 0
                        inicio_estavel = t0
                    concluidos += 1
                    if concluidos >= pedidos:
                        duracao = time.perf_counter() - inicio_estavel
                        parar.set()
                elif len(amostras) >= pedidos * 3:
                    duracao = time.perf_counter() - t0
                    parar.set()  # erros demais: aborta em vez de girar para sempre

        tarefas = [asyncio.create_task(cliente(i)) for i in range(clientes)]
        await parar.wait()
        for tarefa in tarefas:
            tarefa.cancel()  # fecha as conexões; o gateway cancela os pedidos em andamento
        await asyncio.gather(*tarefas, return_exceptions=True)
    return amostras, duracao


def gravar_csv(caminho: Path, amostras: list[Amostra], extras: dict[str, object]) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    colunas = list(extras) + [f.name for f in fields(Amostra)]
    with caminho.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=colunas)
        writer.writeheader()
        for amostra in amostras:
            writer.writerow({**extras, **asdict(amostra)})


def resumo(amostras: list[Amostra], duracao: float) -> dict[str, float | int | None]:
    ok = [a for a in amostras if a.status == "ok" and not a.transiente]
    ttfts = sorted(a.ttft_ms for a in ok if a.ttft_ms is not None)
    tokens = [a.tokens for a in ok if a.tokens is not None]
    return {
        "concluidos": len(ok),
        "transientes": sum(1 for a in amostras if a.transiente),
        "erros": sum(1 for a in amostras if a.status != "ok"),
        "duracao_s": round(duracao, 3),
        "ttft_medio_ms": round(sum(ttfts) / len(ttfts), 1) if ttfts else None,
        "ttft_p95_ms": ttfts[min(len(ttfts) - 1, int(0.95 * len(ttfts)))] if ttfts else None,
        "tokens_por_s_agregado": round(sum(tokens) / duracao, 3) if tokens and duracao > 0 else None,
        "pedidos_por_s": round(len(ok) / duracao, 4) if duracao > 0 else None,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--url", required=True, help="endereço do gateway, ex.: https://127.0.0.1:8443")
    p.add_argument("--token-file", type=Path, help="arquivo com o token do usuário (o lab.py cria)")
    p.add_argument("--ca", type=Path, help="certificado da CA local, para HTTPS")
    p.add_argument("--clientes", type=int, required=True)
    p.add_argument("--pedidos", type=int, default=30, help="pedidos concluídos por execução")
    p.add_argument("--dominio", default="redes")
    p.add_argument("--perguntas", type=Path, default=AQUI / "perguntas.txt")
    p.add_argument("--max-tokens", type=int, default=128, help="tamanho dos pedidos (longos)")
    p.add_argument("--max-tokens-curto", type=int, default=32)
    p.add_argument("--fracao-curtos", type=float, default=0.0, help="0 = todos iguais; 0.5 = metade curtos")
    p.add_argument("--sem-aquecimento", action="store_true")
    p.add_argument("--descartar", type=int, help="pedidos concluídos do transitório (padrão: N)")
    p.add_argument("--semente", type=int, default=1)
    p.add_argument("--saida", type=Path, required=True)
    p.add_argument("--rotulo", action="append", default=[], help="coluna extra no CSV, ex.: k=1")
    args = p.parse_args(argv)
    token = args.token_file.read_text(encoding="utf-8").strip() if args.token_file else None
    amostras, duracao = asyncio.run(
        rodar(
            url=args.url.rstrip("/"), token=token, ca=args.ca, clientes=args.clientes,
            pedidos=args.pedidos, dominio=args.dominio, perguntas=ler_perguntas(args.perguntas),
            tokens_curto=args.max_tokens_curto, tokens_longo=args.max_tokens,
            fracao_curtos=args.fracao_curtos, aquecimento=not args.sem_aquecimento, semente=args.semente,
            descartar=args.descartar,
        )
    )
    extras: dict[str, object] = {"clientes": args.clientes, "duracao_s": round(duracao, 4)}
    for item in args.rotulo:
        chave, _, valor = item.partition("=")
        extras[chave] = valor
    gravar_csv(args.saida, amostras, extras)
    print(json.dumps(resumo(amostras, duracao), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
