# Projeto 1 — Gateway distribuído de LLMs abertos

**Disciplina:** Redes de Computadores · **UFES**
**Estado:** M1 implementado; incrementos de M2 implementados em perfis próprios e exercitados com backends simulados e modelos reais. Avaliação clínica humana, comparação quantitativa de políticas e experimento M3 ainda estão pendentes. Veja [Estado de implementação](#estado-de-implementação).

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
| Balanceamento: round-robin, menor fila, menor latência (EWMA) | **Implementado**; políticas têm testes unitários e o perfil `m2_replicas.toml` fornece réplicas equivalentes |
| Falha de backend | **Implementada**: retira nó indisponível, tenta uma réplica compatível uma vez antes do primeiro delta; mid-stream termina com erro parcial. Ambos verificados com runtime real |
| Segurança: token, autorização por domínio, rate limit e TLS | **Implementada** no perfil M2; inclui token provisionado por CLI, `/metrics` restrito e CA validada pelo cliente |
| Roteamento `auto` e escolha pequeno/maior | **Implementado como piloto**: TF-IDF + regressão logística, 120 exemplos sintéticos e split agrupado. A acurácia do conjunto pequeno não representa generalização |
| Comparação quantitativa RR × menor fila × menor latência sob carga real | **Pendente**; implementação e configuração existem, falta executar matriz controlada |
| Carga fechada 1/2/4/8/16, previsão de fila, repetições, gráficos | **Não implementado (M3)** |
| Pipeline dos 500 pares AnonyMED-BR, splits, amostra humana, exportação CSV/JSON | **Não implementado (F3)**. `data/anonymedbr/` permanece ignorado e não foi alterado |

## Ambiente reprodutível (sem instalação imperativa no sistema)

Tudo fica em `.devenv/` e no venv do projeto. Nada é instalado globalmente.

- [`devenv.yaml`](devenv.yaml) e [`devenv.nix`](devenv.nix): nixpkgs-unstable (travado em [`devenv.lock`](devenv.lock)), Python 3.13, `llama-cpp` (llama-server build 11960, commit 8642541), curl, jq, openssl.
- [`pyproject.toml`](pyproject.toml): dependências Python (FastAPI, uvicorn, httpx, pydantic, scikit-learn) e de desenvolvimento (pytest, ruff), instaladas no venv em modo editável.

```bash
devenv shell          # entra no ambiente (cria o venv na primeira vez)
```

## Modelos

Os pesos ficam em `models/` (fora do versionamento). Os SHA-256 abaixo foram conferidos contra os metadados do Hugging Face.

| Id no config | Arquivo | Origem (commit) | Quant. | Tamanho | SHA-256 | Licença | Uso |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `qwen3-1.7b` | `models/Qwen3-1.7B-Q4_K_M.gguf` | `unsloth/Qwen3-1.7B-GGUF` @ `d7f544ee` | Q4_K_M | 1,03 GiB | `b139949c…181897` | Apache-2.0 (Qwen3-1.7B) | modelo pequeno para ambos os domínios |
| `qwen35-4b` | `models/Qwen3.5-4B-Q4_K_M.gguf` | `unsloth/Qwen3.5-4B-GGUF` @ `e87f1764` | Q4_K_M | 2,55 GiB | `00fe7986…ef11a4` | Apache-2.0 (Qwen3.5-4B) | modelo maior para ambos os domínios |

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

Os dois runtimes do perfil mínimo ocuparam cerca de **6,3 GiB de RSS agregado** na medição local. `RSS` não equivale à memória física exclusiva, pois GGUF usa mmap. Ajuste `threads`, `ctx_size` e `max_inflight` para sua máquina.

## Perfil M2: segurança, inteligência e réplicas

O perfil `configs/m2_secure.toml` habilita TLS obrigatório, token Bearer, autorização por domínio, rate limit, roteamento semântico e escolha de tamanho de modelo. O modelo pequeno atende ambos os domínios com o schema clínico obrigatório; o padrão do domínio continua distinto (`redes` pequeno, `prontuario` maior). **Não exponha credenciais nem a CA local.**

Prepare o certificado e crie um token (o comando mostra o segredo uma única vez; o arquivo contém apenas seu SHA-256 e tem modo `0600`):

```bash
scripts/generate-local-ca.sh
llm-gateway token-create \
  --users-file secrets/users.toml \
  --username integrante-a \
  --domains redes,prontuario \
  --requests-per-minute 120 --burst 16 --metrics
```

Guarde o token fora do repositório e exporte-o sem colocá-lo na linha de comando:

```bash
read -rsp 'Token do gateway: ' LLM_GATEWAY_TOKEN; export LLM_GATEWAY_TOKEN; echo
```

Em terminais separados, rode os runtimes de `redes-1` e `prontuario-1` e depois o gateway. Todos os comandos devem ser executados dentro do mesmo ambiente devenv:

```bash
llm-gateway runtime --config configs/m2_secure.toml --node redes-1
llm-gateway runtime --config configs/m2_secure.toml --node prontuario-1
llm-gateway serve --config configs/m2_secure.toml
```

Chamada autenticada: o cliente lê o token de ambiente e valida o certificado local pela CA; não há opção `verify=False`.

```bash
llm-gateway-client --url https://127.0.0.1:8080 --ca artifacts/tls/ca.crt \
  --domain auto --input 'O que é TCP?' --json
curl --cacert artifacts/tls/ca.crt \
  -H "Authorization: Bearer $LLM_GATEWAY_TOKEN" \
  https://127.0.0.1:8080/metrics | jq .
```

Para duas réplicas equivalentes do modelo pequeno, use `configs/m2_replicas.toml`: `redes-1` na porta 8101 e `redes-2` na 8103, mais o nó de 4B. É uma topologia de **mesmo host** e não cria capacidade física; na máquina de desenvolvimento o RSS agregado dos três processos chegou a cerca de 8,4 GiB (o valor agregado conta páginas mmap compartilhadas mais de uma vez). Não é o perfil recomendado para uma máquina de 8 GB.

## Protocolo

`POST /v1/generate` com `Content-Type: application/json` e `Accept: text/event-stream`:

```json
{"domain": "prontuario", "input": "texto sintético do prontuário", "max_output_tokens": 768}
```

Campos extras (`model`, `prompt`, `schema`, `system`) são rejeitados com 422. O cliente não escolhe prompt, modelo nem schema.

| Evento | Conteúdo |
| --- | --- |
| `meta` | `request_id`, domínio pedido/resolvido, `model`, `node`, hash de prompt, schema, fila, tentativa e confiança do roteador |
| `delta` | `seq`, `text`: trecho gerado, enviado assim que chega. Não é necessariamente um token |
| `result` | `schema`, `data`: só em `prontuario`, após validação do JSON completo |
| `done` | `finish_reason`, `completion_tokens`, `tokens_source` (`backend_usage` ou `deltas`) |
| `error` | `code`, `message`, `partial` (já houve delta), `retryable` |

Comentários `: keepalive` são enviados durante a espera na fila. Não são tokens e não contam como TTFT.

Códigos HTTP antes do stream: `400 unknown_domain`, `401` sem/com token inválido, `403 domain_forbidden`, `413 body_too_large` / `input_too_large`, `422 invalid_request` / `max_output_tokens_exceeds_limit` / `domain_uncertain`, `426 tls_required`, `429 rate_limited`, `503 queue_full` ou `no_healthy_nodes`. Quando a conexão já abriu, falhas aparecem como evento `error`.

Códigos de `error`: `backend_unavailable`, `backend_timeout`, `backend_error`, `incomplete_stream`, `truncated` (limite de tokens atingido), `schema_invalid`, `queue_timeout`, `deadline_exceeded`, `client_too_slow`.

## Métricas

Os tempos usam relógio monotônico do processo. Cada tentativa gera uma linha em `artifacts/logs/requests.jsonl` com status, código de erro, pseudônimo de usuário, rota solicitada/resolvida, modelo, nó, número de tentativa, profundidade da fila, tempos, tokens e `partial_output_discarded`. O log não contém token, texto de entrada, saída ou prompt.

Definições:

- **TTFT gateway:** admissão → primeiro delta do backend. **TTFT cliente:** envio → primeiro delta não vazio recebido.
- **Tokens/s de decodificação:** `(n−1)/(t_último − t_primeiro)`, com `n` = tokens reportados pelo runtime (`backend_usage`). Indefinido se `n<2`.
- Se o runtime não informar `usage`, `tokens_source=deltas`: o número é de deltas, não de tokens.

## Testes

```bash
devenv shell -- pytest          # 81 testes; backends simulados/MockTransport, mais TLS local; sem baixar modelos
devenv shell -- ruff check src tests
```

Cobertura atual: validação de configuração; protocolo SSE; schema; escalonador; backends; API e cancelamento; auth 401, autorização 403, rate limit 429; TLS com CA válida e não confiável; roteamento e baixa confiança; bypass de autorização por `auto`; balanceadores e fallback em réplica antes do primeiro delta; falha após delta sem concatenação.

Os testes não substituem medições com LLM real. Eles validam o comportamento de filas, SSE e falhas.

## Medições de smoke (não são benchmark)

Execuções únicas feitas durante a implementação, para verificar o caminho ponta a ponta. **Não tiram conclusões sobre desempenho.** Máquina de desenvolvimento: 12 núcleos, 15 GiB de RAM, sem GPU; as configurações usaram 4 threads por runtime.

| Teste | Resultado |
| --- | --- |
| Redes, Qwen3 1.7B, pergunta curta | 30 tokens; TTFT cliente ~3,0 s (inclui prefill do prompt de sistema); geração ~10,7 tok/s |
| Prontuário, Qwen3.5 4B, texto sintético de ~420 caracteres | 250 tokens de saída; `result` válido; ~68 s de serviço; TTFT cliente ~0,6 s em execução já aquecida |
| Três clientes simultâneos em Redes (1 slot) | Profundidade de fila na admissão 0, 1, 2; espera na fila ~0, 5,8 e 11,6 s, consistente com o serviço anterior (FIFO serial) |
| Morte do runtime de Redes durante o stream (118 deltas recebidos) | Cliente: `error` `backend_error`, `partial=true`, `retryable=true`, sem `done`. Log: `partial_output_discarded=true` |
| TLS M2 | CA local validada pelo cliente; cliente sem a CA rejeitado; métricas autenticadas, domínio não autorizado recebeu 403 |
| Failover em runtime real (duas instâncias Qwen3 equivalentes) | Nó 1 indisponível antes da geração; retry no nó 2, `attempt_nodes=[redes-1, redes-2]`; resposta completou |
| Queda real de Qwen3.5 durante geração | Cliente recebeu `backend_error`, `partial=true`, sem `done`; não concatenou outra resposta |
| Roteamento semântico real | Pedido simples de Redes → Qwen3 1.7B; pedido simples clínico → schema JSON no Qwen3 1.7B; pedido complexo → Qwen3.5 4B |

Observações registradas para as fases seguintes:

- **Fidelidade da extração:** no texto de teste, "hipótese diagnóstica de bronquite aguda" virou "bronquite aguda" na saída. A regra 5 do prompt pede preservar a hipótese. Isso precisa ser medido em F3, não corrigido por suposição.
- **Fidelidade do modelo pequeno:** em um smoke de extração simples, o Qwen3 1.7B criou a queixa "Pneumonia", ausente no texto, embora o JSON passasse no schema. O roteador de complexidade **não é um avaliador de qualidade**; este modelo não deve ser considerado apto para uso clínico.
- **Acurácia do roteador:** 100% em domínio e complexidade em 32 exemplos de teste agrupados por tópico, extraídos de 120 frases curtas geradas por templates. É uma verificação do pipeline, não evidência de generalização. Faltam frases variadas e avaliação externa.
- **Espaço em branco no JSON:** a saída pretty-printed gera muitos tokens (250 para um registro pequeno). Vale medir uma forma compacta antes da calibração de carga.
- **Contexto:** `ctx_size = 4096` e `max_input_chars = 8000` são estimativas. Falta calibrar com a contagem de tokens do próprio modelo (F1).

## Limitações conhecidas

- Um único processo de gateway e filas/rate limit em memória: reiniciar o gateway descarta as filas e os buckets. Uvicorn deve permanecer com um worker.
- O failover automático é limitado a uma réplica compatível, uma vez, e somente antes do primeiro delta; mid-stream é erro parcial explícito.
- O perfil `cpu_minimal.toml` é HTTP sem auth/TLS, destinado a localhost. Para M2, use `m2_secure.toml`; `/metrics` requer token com permissão específica.
- O health check tira nós falhos da elegibilidade e os reinsere quando `/health` retorna 200. A descoberta ocorre após uma falha do backend, não é um detector distribuído de falhas.
- Nenhum benchmark M3 foi executado; smoke tests não substituem repetições nem medições controladas.

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
configs/m2_secure.toml                 auth + autorização + rate limit + TLS + router
configs/m2_replicas.toml               mesmo perfil M2 com segunda réplica Qwen3
data/routing_examples.jsonl            120 exemplos de roteamento totalmente sintéticos
src/llm_gateway/
  api.py            FastAPI: /v1/generate (SSE), /health, /v1/domains, /metrics
  gateway.py        registro de nós por domínio e admissão
  scheduler.py      fila explícita por nó: despacho, expiração, cancelamento, eventos
  balancing.py      políticas round_robin / least_loaded / least_latency
  security.py       token Bearer, autorização, token bucket e provisionamento
  routing.py        TF-IDF + regressão logística, confiança e complexidade
  backends/         llama_server (HTTP/SSE) e simulated (somente testes)
  clinical/         schema v1 do prontuário e validação
  prompts.py        prompts de sistema versionados e montagem das mensagens
  protocol.py       requisição, codificação e leitura de SSE
  jobs.py           estado de cada requisição e métricas derivadas
  metrics.py        log JSONL e estatísticas por nó
  config.py         configuração validada (TOML)
  cli.py            llm-gateway serve | runtime | check-config | token-create
  client.py         llm-gateway-client
scripts/            geração de CA local e dataset sintético do roteador
tests/              suíte de 81 testes
data/anonymedbr/    dados preservados (não modificados)
models/             pesos GGUF (ignorados pelo git)
artifacts/          logs e resultados gerados (ignorados pelo git)
```

## Próximos passos

1. **M2 — Desempenho:** medir RR × menor fila × menor latência em réplicas reais equivalentes, com recursos fixos e repetições; registrar limites do mesmo host.
2. **M2 — Inteligência:** ampliar o conjunto de roteamento, separar famílias linguísticas, avaliar em exemplos escritos independentemente e medir qualidade/custo do modelo pequeno versus grande.
3. **F3 — Dados:** adapter dos 500 pares por ID, splits 100/400 com seed, amostra de 60 para revisão humana, exportação JSON/JSONL/CSV e medição de fidelidade por campo. Só após resolver permissões de uso/publicação.
4. **M3 — Experimento:** carga fechada N=1/2/4/8/16, previsão prévia, cinco repetições e gráficos regeneráveis; incluir FIFO versus prioridade com aging.
