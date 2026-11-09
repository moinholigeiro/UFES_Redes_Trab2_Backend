# Projeto 1 — Gateway distribuído de LLMs abertos (Backend)

Redes de Computadores (INF16158) · UFES · Prof. Magnos Martinello · equipe: Daniel, Lívia e Eduardo.

Um gateway recebe pedidos de vários clientes, coloca cada um na **fila do nó de inferência** certo para o domínio e
devolve a resposta **token a token** por **SSE**. Os modelos são de pesos abertos (Qwen3 1.7B e Qwen3.5 4B) e rodam
localmente no `llama-server` (llama.cpp). Dois domínios: **`redes`**, um assistente da disciplina, e
**`prontuario`**, que extrai um JSON validado de um prontuário **sintético**.

> Sistema acadêmico. Não use para diagnóstico ou qualquer decisão de saúde. Só dados sintéticos.

## Os três repositórios

| Repositório | O que tem |
|---|---|
| **UFES_Redes_Trab2_Backend** (este) | Gateway: API, fila, balanceamento, failover, segurança, métricas, experimentos, `lab.py` |
| UFES_Redes_Trab2_LLM | Nós de inferência: `node.py` valida config e modelo e inicia o `llama-server` |
| UFES_Redes_Trab2_Frontend | Tela web (JS puro), servida pelo próprio gateway |

Os três ficam **lado a lado na mesma pasta**. O diagrama e o código explicados estão em [EXPLICACAO.md](EXPLICACAO.md).

## Rodar em um comando

```bash
python3 lab.py demo          # dois modelos, gateway e tela nesta máquina (~6 GB de RAM)
python3 lab.py demo --leve   # um modelo só (~2 GB de RAM)
```

Na primeira vez, o `lab.py` cria o ambiente Python, baixa o `llama-server` e os modelos (com SHA-256 conferido) e gera o
token e o certificado. Depois ele imprime a URL (`https://127.0.0.1:8443`) e o token para colar na tela. Ctrl+C encerra.

**No laboratório**, com várias máquinas e sem credencial do GitHub: [docs/LABORATORIO.md](docs/LABORATORIO.md).

## Desenvolvimento

```bash
python3 -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[dev,router,experiments]"
python -m pytest -q                                  # ~140 testes, backends simulados, sem modelo
ruff check src tests experiments lab.py
```

O CI do GitHub Actions roda os dois a cada push. O `devenv` (Nix) continua funcionando para quem preferir.

## O que o trabalho entrega, item a item da spec

| Item da spec | Onde está |
|---|---|
| Protocolo com resposta token a token | `POST /v1/generate` com SSE — [contrato v1.1](contracts/public/v1/README.md) |
| Dois domínios com modelo, prompt e parâmetros próprios | `configs/*.toml`, `src/llm_gateway/prompts.py` |
| Fila por nó com limite de concorrência | `scheduler.py` (K vagas por nó) + `queue_policy.py` (FIFO ou curtos primeiro) |
| Métricas: TTFT, tokens/s, latência, vazão | `jobs.py`, `metrics.py`, `GET /metrics`, CSVs do experimento |
| **Desempenho:** 3 políticas de balanceamento + failover | `balancing.py`, `gateway.py` (refaz antes do 1º trecho, migra a fila de nó que caiu) |
| **Segurança:** token, autorização por domínio, limite de taxa, TLS | `security.py`; TLS no gateway; chave de API entre gateway e nós |
| Inteligência (opcional, desligado) | `routing.py` — `pip install -e .[router]` |
| Experimento obrigatório (N = 1…16, previsão antes) | `python3 lab.py experimento` → `experiments/` |
| Pergunta-desafio (FIFO × curtos primeiro) | `python3 lab.py experimento --desafio` |

## Endpoints

| Rota | Para quê |
|---|---|
| `POST /v1/generate` | Pedido `{domain, input, max_output_tokens?}` → stream SSE `meta`, `queued`, `delta`, `result`, `done`, `error` |
| `GET /health` · `GET /ready` | Processo vivo · existe nó saudável |
| `GET /v1/domains` | Domínios disponíveis |
| `GET /metrics` | Fila, vagas, falhas e vazão de cada nó (token com permissão) |
| `GET /` | A tela (quando `gateway.frontend_dir` está configurado) |

Não há banco de dados: fila e estado ficam em memória (um processo, um worker). O disco guarda só o log JSONL de cada
tentativa (`artifacts/logs/requests.jsonl`, sem texto de entrada ou saída) e os hashes dos tokens.

## Documentação

| Documento | Conteúdo |
|---|---|
| [EXPLICACAO.md](EXPLICACAO.md) | Diagramas (repositórios, camadas, fluxo, máquinas) e o código explicado; perguntas de entrevista |
| [docs/PLANO.md](docs/PLANO.md) | Plano v2: requisitos, decisões técnicas D0–D19, cenários de máquinas |
| [docs/MUDANCAS.md](docs/MUDANCAS.md) | O que mudou em 09/11, por quê, e como conferir |
| [docs/LABORATORIO.md](docs/LABORATORIO.md) | Tutorial do laboratório |
| [docs/RELATORIO-ESQUELETO.md](docs/RELATORIO-ESQUELETO.md) | Estrutura do relatório de 6 páginas |
| [experiments/README.md](experiments/README.md) | Experimento: previsão, execução, gráficos |
| [docs/ENUNCIADO.md](docs/ENUNCIADO.md) | Spec do professor (21/10) |
| [CHANGELOG.md](CHANGELOG.md) | Histórico de mudanças |
| [docs/historico/](docs/historico/) | Planos e README anteriores, preservados |

## Limitações conhecidas

- Um processo de gateway: reiniciar descarta filas e limites de taxa.
- Failover automático só antes do primeiro trecho; depois dele, o cliente recebe `error` com `partial=true`
  (decisão D9 do plano). Pedidos que ainda esperavam na fila do nó que caiu migram para outra réplica.
- O roteador semântico é um piloto com 120 frases sintéticas; a acurácia dele não representa generalização.
- Dados do AnonyMED-BR ficam fora do T2 (licença pendente).
