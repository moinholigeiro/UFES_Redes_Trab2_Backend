# Explicação do código — Backend

Este documento acompanha a implementação atual do gateway. “Trecho” significa uma unidade lógica do arquivo — imports/constantes, classes, funções, rotas ou blocos de responsabilidade — e não uma repetição linha a linha do código. Os caminhos são relativos à raiz deste repositório.

## 1. Visão geral do fluxo

1. `cli.py` carrega e valida TOML com `config.py`, depois inicia um único worker Uvicorn.
2. `api.py` autentica/admite `POST /v1/generate`, valida o corpo, resolve domínio/modelo e cria um `Job`.
3. `gateway.py` seleciona um nó compatível por meio de `balancing.py`; cada nó tem um `NodeScheduler` em `scheduler.py`.
4. O adapter (`backends/llama_server.py` ou `backends/simulated.py`) produz `Delta` e `Finish` conforme `backends/base.py`.
5. O scheduler valida e guarda o resultado necessário, produz eventos públicos e registra métricas. `api.py` converte-os para SSE; `client.py` é um cliente terminal de referência.

O gateway é o único dono de filas, concorrência, seleção de nós e failover. Os backends de inferência não tomam decisões de roteamento.

## 2. Pacote `src/llm_gateway/`

### `__init__.py`

Declara a versão do pacote (`0.1.0`) e sua descrição curta; não inicializa serviços.

### `config.py` — configuração e validação

- `_Strict`: base Pydantic que proíbe chaves desconhecidas e congela os objetos validados.
- `GatewayConfig`: limites de corpo/entrada/saída, deadlines, tempos de espera, health probes, buffer SSE, arquivos TLS, CA, CORS e limite do header de autenticação. Os validadores verificam origens CORS exatas, par cert/key, números finitos e coerência entre timeouts.
- `SecurityConfig`: habilitação de autenticação, arquivo de credenciais, exigência de TLS e campos de rate/burst para validação/defaults; o rate efetivamente aplicado a cada usuário vem do arquivo de credenciais.
- `RouterConfig`: ativa o classificador e define thresholds, seed e fração de avaliação.
- `BalancingConfig`: política permitida e máximo de tentativas de failover.
- `ModelConfig`: metadados do modelo, contexto e formato/hash SHA-256.
- `DomainConfig`: prompt, modelos permitidos, saída textual ou extração JSON, parâmetros de amostragem e limites de tokens; garante que prompt/schema/modelos e defaults sejam consistentes.
- `SimulationConfig`: atraso, velocidade, resposta e ponto de falha para testes; não representa inferência real.
- `NodeConfig`: identidade, URL, modelo, concorrência, limites de frame/saída e kwargs de template. Valida URL, porta, credenciais/path e restringe HTTP a loopback.
- `AppConfig`: valida as relações entre nós, modelos, domínios, roteador, simulação e trust bundle obrigatório para endpoints HTTPS.
- `load_config(path)`: lê TOML e devolve a configuração tipada ou falha antes de iniciar o serviço.

### `api.py` — HTTP, lifespan, admissão e SSE

- `_Reject`: carrega status HTTP, código/mensagem estáveis e headers adicionais para erros pré-stream.
- `_error_response(...)`: forma envelope JSON uniforme `{error: ...}`.
- `_read_limited(request, limit)`: consome o corpo em blocos e interrompe assim que excede o limite em bytes.
- `_event_stream(...)`: lê a fila de eventos do job, envia comentários keepalive, tenta failover somente quando o erro é elegível e ainda não houve delta, sintetiza `meta` antes do primeiro evento e encerra no primeiro `done`/`error`. Ao detectar desconexão do cliente, pede cancelamento do job.
- `create_app(config)`: constrói a aplicação FastAPI e seu ciclo de vida. No startup, cria cliente HTTPX com verificação TLS/CA, adapters, `Gateway`, gerenciador de segurança/roteador e schedulers. Probes concorrentes consultam `/health` com timeout; shutdown cancela probes, schedulers e fecha logs/HTTP.
- `_on_reject`: converte exceções de admissão em respostas HTTP.
- `_principal`: limita o tamanho do Authorization antes do hash, autentica token e, para métricas, exige permissão específica.
- `GET /health`: liveness simples do processo.
- `GET /ready`: retorna 200 se algum scheduler está saudável, 503 caso contrário; não certifica, por si só, compatibilidade de hash/template/slots.
- `GET /v1/domains`: publica catálogo público dos domínios e formato de saída.
- `GET /metrics`: rejeita HTTP se TLS for obrigatório, verifica autorização e devolve snapshot de nós/roteador sem textos de entrada ou saída.
- `POST /v1/generate`: aplica TLS/auth/rate limit; inicia deadline no recebimento, limita leitura do corpo pelo menor tempo entre timeout configurado e prazo restante, valida DTO e limites; resolve somente `domain=auto` com o classificador; autoriza o domínio resolvido; monta mensagens de sistema; cria/admite `Job`; devolve erros HTTP distintos ou stream SSE com `X-Request-ID`.
- `create_app_from_env()`: fábrica para Uvicorn que recupera o caminho TOML de `LLM_GATEWAY_CONFIG`.

### `jobs.py` — estado, falhas e relógios

- `JobState` e `TERMINAL_STATES`: estados não terminais/terminais da requisição.
- `RETRYABLE_CODES`: orientação pública para o cliente poder iniciar uma nova requisição; não autoriza automaticamente replay.
- `FAILOVER_CODES`: allowlist mais restrita, só para falhas transitórias entre gateway e nó.
- `JobError`: exceção com código e mensagem seguros para o protocolo.
- `_ms`: transforma dois tempos monotônicos em milissegundos ou devolve `None`.
- `Job`: mantém request ID, domínio/modelo, mensagens, orçamento, fila de eventos, deadline, tentativas, timestamps, contadores, token usage e task. Métodos calculam estado terminal, espera de fila, TTFT, serviço, E2E e taxa de decode apenas quando há usage e intervalo válidos.

### `gateway.py` — seleção e failover

- `NoHealthyNodes`: sinaliza que não existe scheduler saudável para a seleção pedida.
- `Gateway.__init__`: constrói um scheduler por nó e lista de nós por domínio, além do balanceador.
- `start()` / `stop()`: inicia/encerra dispatchers e fecha o log.
- `admit(job)`: escolhe o modelo default/solicitado, filtra nós saudáveis compatíveis e tenta admissão na ordem do balanceador; distingue ausência de nós de fila cheia.
- `retry_before_first_delta(job)`: depois de encerrada a tentativa anterior, exige zero deltas, código permitido, prazo ainda válido e limite de tentativas; escolhe outra réplica do mesmo modelo. Não refaz job expirado nem erro determinístico.
- `cancel(job, reason)`: delega cancelamento ao scheduler proprietário.
- `snapshot()`: expõe política, domínios e estado agregado dos nós.

### `scheduler.py` — fila FIFO de cada nó

- `Overloaded`: capacidade de fila/slots esgotada.
- `NodeScheduler.__init__`: armazena backend/config, estatísticas, fila FIFO, ativos, health e evento de despertar. Nós simulados começam saudáveis; nós reais aguardam probe.
- Propriedades `pending_count`, `active_count`, `in_system`: contam filas e reserva de capacidade.
- `start()` / `stop()`: controla dispatcher e cancela jobs/tasks no shutdown.
- `admit(job)`: reserva atomicamente uma vaga no event loop, atribui nó/modelo/tentativa e enfileira; rejeita acima de `max_inflight + max_queue`.
- `cancel(job, reason)`: remove jobs pendentes ou cancela a task ativa e registra o motivo.
- `_dispatch_loop()`: acorda periodicamente, expira pendentes, não despacha em nó não saudável e respeita FIFO, slots e deadline.
- `_expire_pending()`: remove pendentes vencidos por deadline total ou queue timeout e envia erro terminal.
- `_start(job)`: marca ACTIVE, grava dispatch e cria a task de processamento.
- `_run(job)`: aplica deadline total ao backend, classifica timeout/erro/cancelamento, fecha estado/slot e registra métricas.
- `_stream(job)`: consome `Delta`/`Finish`; limita bytes UTF-8 de saída, conta trechos e tempos, publica deltas, exige finish `stop`, valida saída clínica se aplicável e reserva espaço para `result` + `done`. A transição DONE e eventos terminais acontecem sem `await` entre eles.
- `_emit(...)`: coloca delta com timeout de cliente lento.
- `_fail(...)`: marca falha, desabilita nó em falhas transitórias específicas e garante evento error mesmo com buffer cheio, contabilizando deltas descartados.
- `_error_payload(...)`: produz código/mensagem/partial/retryable.
- `snapshot()`: relatório de health, slots, fila e contadores.

### `balancing.py` — ordenação de candidatos

- `Balancer.__init__`: aceita `round_robin`, `least_loaded` ou `least_latency` e mantém cursor por domínio.
- `order(domain, candidates)`: RR gira o primeiro escolhido; menor fila ordena por ativos+pendentes e nome; menor latência usa EWMA de serviço e favorece nós ainda sem observação durante warm-up.

### `metrics.py` — estatísticas e JSONL

- `EWMA_ALPHA`: peso da observação nova na média móvel exponencial.
- `NodeStats`: contadores de concluídos/falhas/cancelamentos/expirações/rejeições e atualização de EWMA.
- `RequestLog`: abre arquivo JSONL opcional, grava um registro por tentativa e fecha o descritor.
- `job_record(job)`: serializa estados, identificadores, tempos e contagens sem incluir prompt, entrada, saída ou bearer token.

### `protocol.py` — DTO e SSE

- `TERMINAL_EVENTS`: `done` e `error`.
- `GenerateRequest`: valida domínio/entrada e aceita `max_output_tokens` como inteiro estrito positivo, sem coerção de string/bool.
- `sse_encode(event, data)`: serializa JSON compacto Unicode em formato SSE com linha em branco terminal.
- `sse_comment(text)`: codifica comentário/heartbeat, que não é delta.
- `iter_sse(lines)`: parser síncrono de linhas para o cliente Python; agrega múltiplas linhas `data`, ignora comentários e não emite frame incompleto no EOF.

### `prompts.py` — prompts imutáveis por versão

- `REDES_V1` e `PRONTUARIO_V1`: instruções server-side para os dois domínios; o usuário não pode substituí-las.
- `PROMPTS`: catálogo nomeado.
- `prompt_hash(name)`: hash da versão usada para identificação/auditoria.
- `build_messages(prompt, output, user_input)`: cria mensagens system/user e delimita documento como entrada não confiável; para extração pede JSON.

### `routing.py` — classificador do modo automático

- `RoutingDataError`, `RouteUncertain`: erros de dataset inválido e confiança insuficiente; a incerteza inclui candidatos/probabilidades.
- `RouteDecision`: domínio/modelo escolhido, confiança e classe de complexidade.
- `_pipeline(seed)`: cria pipeline TF-IDF + regressão logística com seed fixa.
- `load_examples(path, known_domains)`: lê JSONL sintético, valida campos/IDs/domínios/complexidades/grupos e separa grupos para evitar vazamento por grupo.
- `SemanticRouter.__init__`: carrega dados, treina no subconjunto de treino e calcula avaliação holdout; isso ocorre ao iniciar quando router está habilitado.
- `_evaluate(...)` / `evaluation()`: calcula acurácia/matriz e publica resumo sem conteúdo dos exemplos.
- `_top(...)`: ordena probabilidades e devolve candidatos principais.
- `route(requested_domain, text)`: combina confiança de domínio e complexidade, aplica thresholds sem arredondar internamente, e resolve modelo permitido pelo domínio; domínio explícito não passa por esta seleção automática.

### `security.py` — Bearer, autorização e rate limit

- `CredentialError`, `RateLimitExceeded`: erros de carregamento e limite, este último com `Retry-After`.
- `UserCredential`, `CredentialFile`: schemas estritos; guarda hash do bearer, domínios permitidos, rate/burst e permissão de métricas.
- `Principal`: identidade autenticada e pseudônimo de auditoria.
- `load_credentials(...)`: lê TOML, valida usuários, hashes únicos e domínios conhecidos; falha fechada.
- `TokenBucket`: bucket por usuário com recarga baseada em monotonic clock.
- `SecurityManager`: compara hash do token em tempo constante, autoriza domínio, aplica rate e decide acesso a métricas.
- `token_digest()` / `new_token()`: derivam SHA-256 e criam segredo opaco de alta entropia.
- `write_credential_file(...)`: valida parâmetros e username, atualiza usuário sem overwrite implícito e escreve TOML atomicamente com permissão restrita.

## 3. Backends de inferência

### `backends/base.py`

Define os tipos imutáveis `Delta(text)` e `Finish(reason, usage)` e o protocolo `Backend.stream(job)`. O scheduler depende deste contrato, não da implementação concreta.

### `backends/__init__.py`

Exporta tipos e `make_backend(node, client)`, que seleciona adapter llama-server ou simulado pela configuração.

### `backends/llama_server.py`

- `LlamaServerBackend.__init__`: compõe endpoint `/v1/chat/completions` e guarda cliente HTTPX compartilhado.
- `_body(job)`: monta mensagens, stream, usage, limite de tokens, sampling e, para schema clínico, `response_format` com JSON Schema.
- `stream(job)`: abre POST streaming, distingue status HTTP, lê eventos do protocolo OpenAI-like, valida tipos/finish/usage/`[DONE]`, emite `Delta`, mapeia falhas HTTP/timeout/protocolo para `JobError` e termina com `Finish`. Uma falha de conexão/transporte pode ser elegível para failover; payload/schema inválidos não devem ser reproduzidos automaticamente.

### `backends/simulated.py`

- `SimulatedBackend.__init__`: divide resposta de fixture em fragmentos semelhantes a palavras.
- `stream(job)`: opcionalmente espera startup, emite fragmentos no ritmo configurado, pode falhar num índice determinístico e fecha com `Finish("stop")`. Serve para regressões, nunca como medição de LLM.

## 4. Extração clínica

### `clinical/__init__.py`

Reexporta o schema e helpers para que API/scheduler importem de um ponto estável.

### `clinical/schema.py`

- `Medicamento`: nome, dose, via e frequência, cada qual explicitamente presente ou `null`; chaves extras são proibidas.
- `SinaisVitais`: valores em texto para manter unidade/fidelidade da fonte.
- `ProntuarioV1`: contrato clínico v1, campos estritos e limites documentados; idade usa `StrictInt` quando informada.
- `SCHEMAS`: mapa de versão.
- `json_schema_for(name)`: exporta schema para constrained decoding no runtime.
- `validate_output(name, text)`: parseia JSON e valida a estrutura completa antes de qualquer evento público `result`.

## 5. CLI e scripts do Backend

### `cli.py`

- `_cmd_serve`: valida config e cert/key quando TLS obrigatório, fixa caminho de config no ambiente e inicia um worker Uvicorn com interpretação de proxy headers desativada.
- `_cmd_check`: carrega config, mostra relações domínio/modelo/nó, valida credenciais/roteador e informa problemas sem iniciar gateway.
- `_cmd_token_create`: cria token e grava somente seu hash; o segredo é exibido para provisionamento.
- `main(argv)`: define subcomandos, argumentos e despacho para o handler.

### `client.py`

- `run_request(...)`: POST síncrono HTTPX, opção CA/Bearer, lê SSE incremental, imprime texto se solicitado, mede tempos locais e produz relatório estruturado. Requer terminal coerente; não transforma erro/parcial em resposta concluída.
- `main(argv)`: valida flags de domínio/arquivo/token/URL, lê entrada e configura saída textual/JSON.

### `scripts/build_routing_dataset.py`

- Constantes de temas e templates criam exemplos sintéticos variados para Redes e extração clínica, em classes simples/complexas.
- `build()`: percorre temas/templates, atribui IDs e grupos por tópico, sinaliza `synthetic=true` e embaralha com seed fixa.
- Bloco principal grava JSONL em `data/routing_examples.jsonl`. O dataset é piloto autoral por templates; não representa holdout independente de linguagem natural.

### `scripts/generate-local-ca.sh`

Valida SANs/duração, usa lock para evitar duas execuções simultâneas, recusa sobrescrever arquivos existentes, gera em diretório temporário uma CA local e certificado TLS do gateway, atribui permissões diferentes a chaves/certificados e só então move os arquivos finais. É para ambiente local, não uma PKI remota.

### `scripts/check-public-contract.sh`

Resolve a raiz Backend e compara byte a byte `contracts/public/v1/events.json` com a cópia do Frontend por `cmp`.

## 6. Contrato, configurações e testes

- `contracts/public/v1/events.json`: schemas JSON dos payloads `meta`, `delta`, `result`, `done` e `error`; não descreve sozinho toda a máquina de estados.
- `contracts/public/v1/README.md`: indica fonte de tipos no Python e regra de sequência/terminais.
- `configs/cpu_minimal.toml`: dois modelos/domínios, HTTP interno em loopback e sem auth/TLS para desenvolvimento controlado.
- `configs/m2_secure.toml`: TLS cliente-gateway, bearer/autorização/rate, router e nós HTTPS sem réplica de Redes.
- `configs/m2_replicas.toml`: perfil seguro com segunda réplica equivalente do modelo pequeno; implica recursos adicionais.
- `tests/conftest.py`: configuração simulada reutilizável, server Uvicorn em thread e fixture HTTP real local.
- `test_config.py`: schemas, referências, limites, perfis e rejeição de URL/config insegura.
- `test_api_sse.py`: rotas, CORS, stream progressivo, extração, fila, cancelamento, falhas e health.
- `test_scheduler.py`: FIFO, limite de concorrência, expiração, cancelamento, parcial, buffers e cliente lento.
- `test_failover.py`: failover em fixture, sem concatenar respostas, erros não elegíveis e deadline.
- `test_llama_backend.py`: contrato HTTP/SSE interno via transporte simulado e erros de protocolo/transporte.
- `test_balancing.py`: ordem das três políticas e fallback de admissão quando a primeira fila enche.
- `test_routing.py`: split/grupos, holdout, confiança, modelo escolhido e integração API.
- `test_security.py`: hash/permissão de credenciais, autenticação, autorização, rate limit, TLS local e exposição de métricas.
- `test_protocol_and_clinical.py`: SSE, DTO estrito e validação JSON clínica.

Os testes simulados/HTTP/TLS local não equivalem a benchmark nem provam inferência real.
