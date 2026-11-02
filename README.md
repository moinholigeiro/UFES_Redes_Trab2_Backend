# Projeto 1 — Gateway distribuído de LLMs abertos

**Disciplina:** Redes de Computadores · **UFES**
**Estado:** **M1 (núcleo) implementado e exercitado com modelos reais.** Incrementos de M2 (segurança, réplicas/failover, roteamento `auto`) e o experimento de M3 ainda **não foram entregues**. Veja [Estado de implementação](#estado-de-implementação).

Gateway que recebe requisições de vários clientes, enfileira por nó e encaminha, em streaming SSE, para runtimes locais de inferência (`llama-server`/llama.cpp). Os domínios são extração estruturada de prontuários sintéticos e um assistente da disciplina de Redes.

> Aviso: sistema acadêmico. **Não use para diagnóstico, tratamento ou qualquer decisão de cuidado em saúde.** Validar JSON não garante veracidade clínica.

Documento de handoff e decisões: [`PLANO_COMPLETO_PROJETO_1.md`](PLANO_COMPLETO_PROJETO_1.md). Enunciado: [`Propostas de Trabalho.md`](Propostas%20de%20Trabalho.md).

## Estado de implementação

| Item | Situação |
| --- | --- |
| Protocolo cliente → gateway: `POST /v1/generate` com SSE (`meta`, `delta`, `result`, `done`, `error`, heartbeat como comentário) | **Implementado** e testado com servidor HTTP real e com `llama-server` real |
| Dois domínios com modelos, prompts e parâmetros distintos (`redes`, `prontuario`) | **Implementado**: Qwen3 1.7B e Qwen3.5 4B, ambos Q4_K_M |
| Extração de prontuário com JSON Schema (geração restrita) e validação ao fim | **Implementado** (schema v1); **qualidade não avaliada** (F3) |
| Fila explícita por nó: `max_inflight`, `max_queue`, expiração, cancelamento, 503 `queue_full` | **Implementado** e testado |
| Cancelamento por desconexão do cliente libera o slot; cliente lento é cortado | **Implementado** e testado |
| Falha durante o stream → `error` com `partial=true`, sem `done` | **Implementado** e **verificado com a morte real do runtime** |
| TTFT, tempo na fila, serviço, latência fim a fim, tokens/s de decodificação, log JSONL por requisição | **Implementado** (sem texto de entrada/saída no log) |
| Balanceamento: round-robin, menor fila, menor latência (EWMA) | **Implementado** e testado em unitário; o perfil mínimo tem um nó por domínio, então a comparação real é de M2 |
| Autenticação por token, autorização por domínio, rate limit, TLS | **Não implementado (M2)** |
| Réplicas no mesmo domínio e failover antes do primeiro delta | **Não implementado (M2)**. O código tem o campo `retryable`, mas não há retry automático |
| Roteamento `auto` (classificador de domínio, escolha pequeno/maior) | **Não implementado (M2)** |
| Carga fechada 1/2/4/8/16, previsão de fila, repetições, gráficos | **Não implementado (M3)** |
| Pipeline dos 500 pares AnonyMED-BR, splits, amostra humana, exportação CSV/JSON | **Não implementado (F3)**. Dados em `data/` não foram alterados |

## Ambiente reprodutível (sem instalação imperativa no sistema)

Tudo fica em `.devenv/` e no venv do projeto. Nada é instalado globalmente.

- [`devenv.yaml`](devenv.yaml) e [`devenv.nix`](devenv.nix): nixpkgs-unstable (travado em [`devenv.lock`](devenv.lock)), Python 3.13, `llama-cpp` (llama-server build 11960, commit 8642541), curl, jq, openssl.
- [`pyproject.toml`](pyproject.toml): dependências Python (FastAPI, uvicorn, httpx, pydantic) e de desenvolvimento (pytest, ruff), instaladas no venv em modo editável.

```bash
devenv shell          # entra no ambiente (cria o venv na primeira vez)
```

## Modelos

Os pesos ficam em `models/` (fora do versionamento). Os SHA-256 abaixo foram conferidos contra os metadados do Hugging Face.

| Id no config | Arquivo | Origem (commit) | Quant. | Tamanho | SHA-256 | Licença | Uso |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `qwen3-1.7b` | `models/Qwen3-1.7B-Q4_K_M.gguf` | `unsloth/Qwen3-1.7B-GGUF` @ `d7f544ee` | Q4_K_M | 1,03 GiB | `b139949c…181897` | Apache-2.0 (Qwen3-1.7B) | domínio `redes` |
| `qwen35-4b` | `models/Qwen3.5-4B-Q4_K_M.gguf` | `unsloth/Qwen3.5-4B-GGUF` @ `e87f1764` | Q4_K_M | 2,55 GiB | `00fe7986…ef11a4` | Apache-2.0 (Qwen3.5-4B) | domínio `prontuario` |

Baixar (a partir da raiz do repositório):

```bash
mkdir -p models
curl -L -C - -o models/Qwen3-1.7B-Q4_K_M.gguf \
  https://huggingface.co/unsloth/Qwen3-1.7B-GGUF/resolve/d7f544eead698dbd1f15126ef60b45a1e1933222/Qwen3-1.7B-Q4_K_M.gguf
curl -L -C - -o models/Qwen3.5-4B-Q4_K_M.gguf \
  https://huggingface.co/unsloth/Qwen3.5-4B-GGUF/resolve/e87f176479d0855a907a41277aca2f8ee7a09523/Qwen3.5-4B-Q4_K_M.gguf
devenv shell -- llm-gateway check-config --config configs/cpu_minimal.toml --verify-models
```

Os repositórios `unsloth/*` são redistribuidores dos GGUF; a licença de cada modelo base deve ser confirmada no model card antes de publicar resultados. Não foram comparados outros candidatos (Gemma 4 E4B, Qwen3 4B) nesta etapa.

## Como executar (perfil mínimo de CPU)

Cada runtime é um processo `llama-server` com **um slot** (`-np` igual a `max_inflight`), para que não haja fila oculta dentro do runtime. Use três terminais, todos dentro de `devenv shell`:

```bash
# terminal 1 — nó de Redes (porta 8101)
llm-gateway runtime --config configs/cpu_minimal.toml --node redes-1

# terminal 2 — nó de prontuário (porta 8102)
llm-gateway runtime --config configs/cpu_minimal.toml --node prontuario-1

# terminal 3 — gateway (porta 8080)
llm-gateway serve --config configs/cpu_minimal.toml
```

Cliente:

```bash
llm-gateway-client --domain redes --input "O que é o three-way handshake do TCP?"
llm-gateway-client --domain prontuario --input-file meu_texto_sintetico.txt --json
curl -s localhost:8080/metrics | jq .      # fila, ativos, concluídos, falhas, cancelados, expirados
```

O cliente imprime o texto progressivamente e, ao final, TTFT e latência medidos no cliente, em JSON na saída de erro. Com `--json`, imprime o relatório completo (metadados, `result`, `done`, `error`).

Os dois runtimes juntos ocupam cerca de **6,9 GB de RSS** (4,6 GB + 2,3 GB, medido com ambos carregados). Para outra máquina, ajuste `threads`, `ctx_size` e `max_inflight` em `configs/cpu_minimal.toml`.

## Protocolo

`POST /v1/generate` com `Content-Type: application/json` e `Accept: text/event-stream`:

```json
{"domain": "prontuario", "input": "texto sintético do prontuário", "max_output_tokens": 768}
```

Campos extras (`model`, `prompt`, `schema`, `system`) são rejeitados com 422. O cliente não escolhe prompt, modelo nem schema.

| Evento | Conteúdo |
| --- | --- |
| `meta` | `request_id`, `domain`, `model`, `node`, `prompt`, `prompt_hash`, `schema`, `queue_depth_at_admission` |
| `delta` | `seq`, `text`: trecho gerado, enviado assim que chega. Não é necessariamente um token |
| `result` | `schema`, `data`: só em `prontuario`, após validação do JSON completo |
| `done` | `finish_reason`, `completion_tokens`, `tokens_source` (`backend_usage` ou `deltas`) |
| `error` | `code`, `message`, `partial` (já houve delta), `retryable` |

Comentários `: keepalive` são enviados durante a espera na fila. Não são tokens e não contam como TTFT.

Códigos HTTP antes do stream: `400 unknown_domain`, `413 body_too_large` / `input_too_large`, `422 invalid_request` / `max_output_tokens_exceeds_limit`, `503 queue_full` (com `Retry-After: 1`). Quando a conexão já abriu, falhas aparecem como evento `error`.

Códigos de `error`: `backend_unavailable`, `backend_timeout`, `backend_error`, `incomplete_stream`, `truncated` (limite de tokens atingido), `schema_invalid`, `queue_timeout`, `deadline_exceeded`, `client_too_slow`.

## Métricas

Os tempos usam relógio monotônico do processo. Cada requisição gera uma linha em `artifacts/logs/requests.jsonl` com status, código de erro, `queue_depth_at_admission`, `queue_wait_ms`, `ttft_gateway_ms`, `service_ms`, `e2e_gateway_ms`, `completion_tokens`, `tokens_source`, `decode_tokens_per_s` e `partial_output_discarded`. O log não contém texto de entrada, saída ou prompt.

Definições:

- **TTFT gateway:** admissão → primeiro delta do backend. **TTFT cliente:** envio → primeiro delta não vazio recebido.
- **Tokens/s de decodificação:** `(n−1)/(t_último − t_primeiro)`, com `n` = tokens reportados pelo runtime (`backend_usage`). Indefinido se `n<2`.
- Se o runtime não informar `usage`, `tokens_source=deltas`: o número é de deltas, não de tokens.

## Testes

```bash
devenv shell -- pytest          # 56 testes; usam backend simulado e MockTransport, sem modelos
devenv shell -- ruff check src tests
```

Cobertura atual: validação de configuração; protocolo SSE; schema de prontuário; escalonador (limite de concorrência, FIFO, capacidade, cancelamento de job em fila e ativo, expiração, deadline, falha mid-stream, cliente lento); backend `llama-server` (SSE, falhas HTTP, EOF sem finish); API com servidor real (progressividade, ordem, Unicode, erros de admissão, 503, heartbeat, desconexão libera slot, log sem entrada); balanceamento e fallback entre réplicas.

Os testes não substituem medições com LLM real. Eles validam o comportamento de filas, SSE e falhas.

## Medições de smoke (não são benchmark)

Execuções únicas feitas durante a implementação, para verificar o caminho ponta a ponta. **Não tiram conclusões sobre desempenho.** Máquina de desenvolvimento: 12 núcleos, 15 GiB de RAM, sem GPU; as configurações usaram 4 threads por runtime.

| Teste | Resultado |
| --- | --- |
| Redes, Qwen3 1.7B, pergunta curta | 30 tokens; TTFT cliente ~3,0 s (inclui prefill do prompt de sistema); geração ~10,7 tok/s |
| Prontuário, Qwen3.5 4B, texto sintético de ~420 caracteres | 250 tokens de saída; `result` válido; ~68 s de serviço; TTFT cliente ~0,6 s em execução já aquecida |
| Três clientes simultâneos em Redes (1 slot) | Profundidade de fila na admissão 0, 1, 2; espera na fila ~0, 5,8 e 11,6 s, consistente com o serviço anterior (FIFO serial) |
| Morte do runtime de Redes durante o stream (118 deltas recebidos) | Cliente: `error` `backend_error`, `partial=true`, `retryable=true`, sem `done`. Log: `partial_output_discarded=true` |

Observações registradas para as fases seguintes:

- **Fidelidade da extração:** no texto de teste, "hipótese diagnóstica de bronquite aguda" virou "bronquite aguda" na saída. A regra 5 do prompt pede preservar a hipótese. Isso precisa ser medido em F3, não corrigido por suposição.
- **Espaço em branco no JSON:** a saída pretty-printed gera muitos tokens (250 para um registro pequeno). Vale medir uma forma compacta antes da calibração de carga.
- **Contexto:** `ctx_size = 4096` e `max_input_chars = 8000` são estimativas. Falta calibrar com a contagem de tokens do próprio modelo (F1).

## Limitações conhecidas

- Um único processo de gateway e filas em memória: reiniciar o gateway descarta as filas.
- Em M1 cada domínio tem um único nó elegível. Não há failover: se o nó cair, novas requisições recebem `backend_unavailable` até o nó voltar.
- O nó derrubado continua elegível até ser reiniciado (não há health check com retirada da elegibilidade).
- Sem autenticação nem TLS: **não exponha a porta 8080 fora de localhost**.
- `/metrics` é público nesta versão; deve ser protegido em M2.
- Nenhum benchmark foi executado; os números acima são de execuções únicas.

## Privacidade e uso dos dados

- Os dados AnonyMED-BR estão em [`data/anonymedbr/`](data/anonymedbr/) e **não foram usados nesta etapa**. O README dessa pasta registra as limitações: anotações geradas e revisadas por LLM, não adjudicação humana.
- **Licença de redistribuição pendente.** Não publique o conjunto, as anotações nem derivados até obter autorização explícita. Crédito ou citação não substituem licença.
- Use somente exemplos sintéticos. O gateway não envia prontuários a serviços externos: toda inferência é local.
- Não registre tokens de acesso nem texto clínico em logs; o log atual não os contém.

## Estrutura

```text
devenv.nix, devenv.yaml, devenv.lock   ambiente reprodutível (nix)
pyproject.toml                         dependências e entrada da CLI
configs/cpu_minimal.toml               perfil mínimo: 2 domínios, 2 modelos, 2 nós
src/llm_gateway/
  api.py            FastAPI: /v1/generate (SSE), /health, /v1/domains, /metrics
  gateway.py        registro de nós por domínio e admissão
  scheduler.py      fila explícita por nó: despacho, expiração, cancelamento, eventos
  balancing.py      políticas round_robin / least_loaded / least_latency
  backends/         llama_server (HTTP/SSE) e simulated (somente testes)
  clinical/         schema v1 do prontuário e validação
  prompts.py        prompts de sistema versionados e montagem das mensagens
  protocol.py       requisição, codificação e leitura de SSE
  jobs.py           estado de cada requisição e métricas derivadas
  metrics.py        log JSONL e estatísticas por nó
  config.py         configuração validada (TOML)
  cli.py            llm-gateway serve | runtime | check-config
  client.py         llm-gateway-client
tests/              suíte de 56 testes
data/anonymedbr/    dados preservados (não modificados)
models/             pesos GGUF (ignorados pelo git)
artifacts/          logs e resultados gerados (ignorados pelo git)
```

## Próximos passos

1. **M2 — Desempenho:** duas réplicas equivalentes no mesmo domínio (perfil de réplicas), comparação RR × menor fila × menor latência e failover antes/depois do primeiro delta com teste de queda real.
2. **M2 — Segurança:** tokens opacos com hash armazenado, autorização por domínio (403), token bucket por usuário (429 com `Retry-After`), TLS com CA local e proteção de `/metrics`.
3. **M2 — Inteligência:** classificador TF-IDF + regressão logística para `auto`, com conjunto de teste reservado; escolha pequeno/maior por critério transparente.
4. **F3 — Dados:** adapter dos 500 pares por ID, splits 100/400 com registro de seed, amostra de 60 para revisão humana, exportação JSON/JSONL/CSV e medição de fidelidade por campo.
5. **M3 — Experimento:** carga fechada com N = 1, 2, 4, 8, 16, previsão de fila salva antes da medição, cinco repetições, gráficos gerados a partir dos brutos.
