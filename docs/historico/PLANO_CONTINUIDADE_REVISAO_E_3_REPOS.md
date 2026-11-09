# Projeto 1 — Revisão, correções e plano completo de continuidade em três repositórios

**Data:** 02/11/2026. **Base revisada:** commit `9371880` da branch `main`.
**Finalidade:** handoff executável para outro agente; não é declaração de funcionalidades entregues.

## 1. Leia antes de agir

Este documento complementa `PLANO_COMPLETO_PROJETO_1.md`. O enunciado em `Propostas de Trabalho.md` continua sendo a fonte normativa acadêmica. A decisão mais recente do usuário é organizar o produto em **três repositórios independentes: frontend, backend e LLM**.

**Um repositório LLM não significa um único processo/modelo/host.** O mesmo código/configuração de implantação será usado por vários nós. O **backend é o gateway e o único proprietário do load balancing, das filas por nó, dos retries e da autorização**. O frontend não escolhe nós e não acessa runtimes diretamente. O repositório LLM não implementa um segundo gateway balanceador.

Nesta revisão só foi solicitado avaliar e produzir este plano. **A separação dos repositórios ainda não foi executada.** Não interpretar o documento como autorização para publicar arquivos, criar remotos ou descartar dados locais. Ao aplicá-lo, realizar a migração local de forma reversível; acesso/publicação no GitHub exige decisão explícita, autenticação e verificação dos arquivos enviados.

### Restrições mantidas

- Python para gateway, clientes e ferramentas. Inferência delegada a `llama.cpp/llama-server`, não reimplementada.
- Alvo de reprodução: Ubuntu, aproximadamente 8 GB RAM, 4 núcleos e sem GPU. A máquina de desenvolvimento tem mais recursos; não confundir isso com viabilidade no alvo.
- GPU de aproximadamente 16 GB VRAM é perfil futuro, não condição para terminar.
- Ambiente declarativo Nix/devenv ou venv local. **Não instalar nada imperativamente no sistema**; não alterar `/etc`, configuração global Git ou confiança global de certificados por iniciativa própria.
- Grupo de três integrantes autorizado pelo professor, conforme decisão já registrada. Não perguntar de novo.
- Um incremento em cada trilha: Desempenho, Segurança e Inteligência. Não retirar silenciosamente nenhum deles.
- Experimento principal em **carga fechada**, N=1/2/4/8/16, previsão anterior à medição, cinco repetições da matriz principal.
- Relatório até seis páginas, demos e discussão TTFT versus tokens/s e FIFO versus prioridade.
- Extração acadêmica, não diagnóstico/recomendação. Não inserir dados reais nem usar APIs externas de inferência como fallback.
- Preservar `data/anonymedbr/`, fontes, anotações e auditorias. Licença de redistribuição pendente; repositório privado também não é licença para redistribuir.
- Frontend agora é parte expressamente solicitada. Mantê-lo pequeno para não consumir o esforço de redes/medidas.

## 2. Resultado da avaliação: faz sentido, mas não está pronto

A arquitetura principal é coerente: FastAPI assíncrono, gateway com filas explícitas, inferência externa residente, SSE progressivo, JSON Schema para extração, autenticação local e seleção de réplicas. Separar em três repositórios faz sentido **se houver independência de implantação e contratos versionados**, não apenas movimentação de pastas.

Não há necessidade de Kubernetes, Redis, Celery, banco ou service mesh para este trabalho. Um backend com um worker e vários runtimes é suficiente inicialmente. Horizontalizar o backend exigiria estado compartilhado e mudaria o dono das filas; isso fica fora do MVP.

### Estado verificado nesta revisão

- Git estava limpo antes de criar este documento. Commits locais: `8a49ce1` (núcleo) e `9371880` (incrementos piloto). Nenhum remoto foi criado nesta tarefa.
- Executados: `devenv shell -- python -m pytest -q -p no:cacheprovider`, Ruff check e Ruff format check: **81 testes passaram**, lint e formatação passaram.
- Os testes são predominantemente simulados/MockTransport, com servidor HTTP e TLS local reais. Passar 81 testes não elimina os problemas listados abaixo.
- Os smokes com GGUF descritos no README foram realizados anteriormente. **Não foram repetidos nesta revisão** e não são benchmark nem medições controladas.
- Nenhum frontend web implementado; cliente atual é CLI síncrono.
- Nenhuma política de prioridade/aging, carga fechada automatizada, previsão, gráficos ou relatório final implementados.
- Modelo pequeno: Qwen3 1.7B Q4_K_M. Maior: Qwen3.5 4B Q4_K_M. Pesos locais ignorados pelo Git.
- Roteador piloto: 120 frases sintéticas por templates, treino=88/teste=32, grupos por tópico. Templates/frases-base são compartilhados entre conjuntos: **não há independência linguística de teste**.
- O modelo pequeno alucinou “Pneumonia” em um smoke, embora o JSON validasse. O maior perdeu uma qualificação de hipótese. Não considerar nenhum deles validado clinicamente.
- Consolidação local conferida em leitura: 500 fontes/500 anotações, IDs-fonte únicos e pareáveis, `synthetic=true`. SHA-256 de `records.jsonl` e `source_records.jsonl` conferem com manifesto. Esse cheque não avalia fidelidade.

### Situação acadêmica conservadora

| Parte | Avaliação |
| --- | --- |
| Núcleo M1 | Existe e tem evidências de streaming/filas, mas métricas de vazão agregada e robustez precisam ser completadas |
| Desempenho M2 | Políticas e retry implementados; comparação real controlada e falhas repetidas faltam; seleção/health/retry têm correções pendentes |
| Segurança M2 | Token, autorização, rate limit e TLS existem; endurecimento, prova contra bypass e demonstração de tráfego cifrado faltam |
| Inteligência M2 | Piloto funcional, não avaliação de generalização; complexo não foi associado a qualidade/custo real |
| Roteiro experimental M2 | Ainda incompleto: sem calibração congelada e previsão salva |
| M3 | Não executado |
| Frontend | Não implementado |
| Dados/extração F3 | Schema existe; adapter, splits, revisão humana, lote/exportação/avaliação faltam |

## 3. Correções prioritárias — antes das medições principais

**P0:** integridade/segurança de execução. **P1:** validade de métricas, contratos e experimento. **P2:** manutenção/ergonomia. As observações por inspeção devem ganhar testes antes de serem consideradas comprovadas em todas as condições.

### C01 — P0 — Finalização do SSE do backend

**Confirmado:** em `backends/llama_server.py`, um stream que entrega `finish_reason=stop` e acaba sem `[DONE]` retorna `Finish('stop', ...)`. Reproduzido com MockTransport nesta revisão. Pode perder o último chunk de usage e mascarar uma conexão interrompida.

**Fazer:** documentar a condição terminal do protocolo interno fixado. Para o runtime atual, exigir `[DONE]`, finish reason consistente e sequência de chunks válida. EOF prematuro vira `incomplete_stream`, sem `result` ou `done` público. Se outro backend tiver convenção diferente, adaptar explicitamente; não relaxar todos os backends.

**Aceite:** testes de EOF antes/depois de finish, usage antes de `[DONE]`, `[DONE]` sem finish, finish incompatível, múltiplas terminações; saída parcial nunca é sucesso.

### C02 — P0 — Exceções não tratadas podem deixar jobs sem evento terminal

**Confirmado:** chunk com `choices` malformado produz `AttributeError` no adapter. `_run()` do scheduler só trata `JobError`, TimeoutError e cancelamento. Erro inesperado pode deixar `state=active` sem job no dicionário de ativos, enquanto o consumidor espera heartbeats indefinidamente.

**Fazer:** validar tipos/estrutura/chunks do protocolo interno, limitar tamanho de frame e resposta HTTP de erro; converter erros esperados em código estável. Ter proteção final contra `Exception` no ciclo do job, nunca engolir `CancelledError`, sempre finalizar estado, emitir erro sanitizado e liberar slot. Detalhes técnicos podem ir a log controlado, sem corpo/token.

**Aceite:** backend malformado, exceção em validação/emit/log, fechamento do generator e Unicode ruim não vazam jobs; exatamente um resultado terminal observável ou cancelamento registrado.

### C03 — P0 — Deadline total e retries

**Inspeção:** deadline começa somente depois de auth, leitura do corpo e classificação. `_expire_pending()` verifica queue timeout, não deadline; um job pode esperar além do deadline até ganhar slot. Retry ignora tempo restante e também é considerado após `queue_timeout`/`deadline_exceeded`, pois usa `retryable` genérico.

**Fazer:** distinguir `received_at`, término da leitura, classificação, enqueue e cada tentativa. Aplicar limites para leitura lenta do corpo e processamento pré-fila; deadline monotônico único para requisição. Expirar pendentes por `min(deadline, attempt_enqueue+queue_timeout)`. Fazer retry automático só para falhas transitórias selecionadas, com prazo restante suficiente; `retryable` do cliente não é autorização para replay interno. Max=1 por padrão. Nunca repetir chamada ainda ativa.

**Aceite:** deadline vence em fila sem despacho, corpo lento é encerrado, retry não renova prazo, zero tentativa após prazo, cancelamento durante transição de réplica não deixa job órfão.

### C04 — P0 — Nó indisponível e capacidade real

**Inspeção:** scheduler inicia `healthy=true`, só alguns códigos marcam indisponibilidade; `backend_error` de morte mid-stream não o faz. Probe só verifica nós já doentes, aceita qualquer HTTP 200 e dispatcher continua despachando pendentes mesmo em nó marcado doente.

**Fazer:** separar liveness/readiness/compatibilidade de modelo e slots; checks iniciais e periódicos leves, com timeout, concorrência limitada, backoff e histerese. Classificar falha de transporte versus erro da requisição/schema. Não marcar nó morto por input inválido; não reinserir por 200 de serviço errado. Impedir despacho para nó não elegível e definir destino dos pendentes (reroute compatível, espera limitada ou erro) mantendo ordem, deadline e métricas. Evitar tempestade de retries.

**Aceite:** nó fora desde startup, morte mid-stream, reinício, endpoint errado, modelo trocado e pendentes na queda; recuperação sem duplicação de execução.

### C05 — P0 — Backpressure precisa ser provado na rede real

**Inspeção:** fila de eventos é limitada por quantidade, mas não por bytes; `parts` acumula toda resposta inclusive em Redes. `client_stall_timeout_s` só limita `queue.put`, não necessariamente o envio ASGI/socket. `_fail()` pode retirar um delta da fila cheia para inserir erro.

**Fazer:** limitar input, frame, output total em bytes e buffer; só acumular o necessário à validação clínica. Medir o comportamento ASGI/socket quando o cliente para de ler. Implementar timeout de envio/consumo compatível com Starlette/Uvicorn e cancelamento upstream. Não eliminar deltas silenciosamente: registrar truncamento de buffer e quantidade gerada/encaminhada/perdida, inclusive diferença entre parcial gerado e parcial recebido.

**Aceite:** consumidor TCP lento e desconectado não retém slot, tasks ou memória; resposta longa maliciosa não cresce indefinidamente. O teste atual de fila cheia simulada é insuficiente sozinho.

### C06 — P0 — Sucesso, result e cancelamento do runtime

**Inspeção:** `result` é enfileirado antes de `done`; erro/timeout posterior pode ocorrer depois do resultado. Cliente CLI imprime `result` mesmo sem `done`. Liberar slot Python não prova que llama-server parou de gerar.

**Fazer:** estado transacional de conclusão. O cliente só exporta após `result` validado **e** `done` consistente. Preview sempre provisório. Finalização do job tem de ser coerente com a entrega do terminal; evitar corrida de `done` seguido de timeout. Testar desconexão HTTP abortando slot no llama-server; se não for instantânea, aguardar readiness do slot ou registrar trabalho residual antes de admitir outro job.

**Aceite:** result+EOF, result+error, corte no último delta, cancelamento durante geração e nova requisição imediata. Sem exportação parcial nem fila oculta no runtime.

### C07 — P1 — Tipos e semântica clínica

**Confirmado:** `ProntuarioV1` aceita `idade='54'` e converte em 54; aceita `idade=true` e converte em 1. Isso não é validação estrita do JSON Schema anunciado.

**Fazer:** validação estrita coerente com o schema publicado; rejeitar boolean/string para idade e outros tipos indevidos. Rever limite 0–130 como restrição documentada, não regra clínica inferida. Evitar mudanças sem versão do schema. Adjudicar alergias desconhecidas versus negação explícita, hipóteses/histórico, nome nulo de medicamento e sexo explicitamente documentado; evitar descartar categorias ou valores escritos só por presumida implausibilidade.

**Aceite:** fixtures de coerção, null/ausência, dose/via/frequência, negações/hipóteses, ranges/unidades e chaves extras. Validade estrutural continua separada de fidelidade.

### C08 — P1 — Rota explícita deve permanecer determinística

**Confirmado:** com router habilitado, requisição `domain=redes` complexa seleciona Qwen3.5 4B, embora `default_model` seja Qwen3 1.7B. Classificação de complexidade altera também domínios explícitos.

**Fazer:** para o contrato conservador escolhido, explícito usa modelo/prompt/parâmetros fixos; `auto` habilita classificação semântica e escolha de tamanho. Se houver futuro modo adaptativo explícito, ele deve ser opção separada, autorizada e documentada. Experimento principal usa explícito/modelo fixo e desliga `auto`, mantendo TLS/rate limit ligados. Não permitir modelo arbitrário enviado pelo cliente.

**Aceite:** mesma entrada em domínio explícito sempre resolve padrão configurado; `auto` simples/complexo pode mudar modelo; permissões verificadas contra domínio resolvido; resultados de baseline não misturam tempos de modelos.

### C09 — P1 — Load balancing comparável e equitativo

**Inspeção:** round-robin tem cursor só por domínio, não por conjunto domínio/modelo; EWMA é global por nó, embora o pequeno/maior atendam ambos os domínios. Warm-up de nós sem observação pode sempre preferir o mesmo nó enquanto não conclui. Menor latência usa serviço global e não considera disponibilidade/fila de forma explicitada.

**Fazer:** chave de elegibilidade/compatibilidade com modelo, hash, runtime, contexto/slots, prompt/schema e perfil de serviço. RR por pool estável; menor fila usa ativos+pendentes; latência utiliza estatística por classe comparável (domínio/modelo e faixa de custo conhecida antes do despacho). Warm-up por reservas/rodízio, desempate estável e exploração documentada. Escolher e registrar se objetivo é serviço ou conclusão esperada incluindo fila; não chamar TTFT de serviço. Retry só em réplica efetivamente compatível, não somente no mesmo alias de modelo.

**Aceite:** testes sob admissão simultânea antes de primeiras conclusões, mudança de pool, workloads mistos, heterogeneidade de slots, ausência de observações e incompatibilidade de hash/template; comparar as três políticas com recursos fixos.

### C10 — P1 — Instrumentação incompleta e fonte dos tokens

**Inspeção:** sem usage, scheduler coloca `completion_tokens=delta_count`; rate `decode_tokens_per_s()` usa esse número mesmo com fonte `deltas`. Uso final e `timings` do backend não são preservados integralmente. Não há vazão agregada, tempo até `result`, timeline de eventos/CPU/PSS/swap, configuração completa/hash ou log separado da requisição lógica.

**Fazer:** `completion_tokens=null` quando desconhecido; `delta_count` separado. Tokenizar saída com tokenizer do mesmo modelo só se possível, marcado como estimativa. Não chamar chunks/tokens ou gerar tok/s a partir de deltas. Preservar usage/timings, perfis e revisões; medir `n/tempo_decode` do backend separadamente de `(n-1)/(t_last-t_first)` do cliente. Documentar delta agrupado e tokens residuais de término.

Criar registros imutáveis de tentativa e um registro final da requisição com todos os retries, tempos locais, resultado utilizável, status e censura. Registrar total produzido versus recebido/útil, distribuição de jobs e erro de admissão (hoje 401/429/503 não entram no log de jobs). Medir sobrecarga do roteador separada do prefill; TTFT gateway atual começa após leitura/classificação, não na recepção. Logging síncrono com flush por job bloqueia event loop: fila de log limitada e writer/estratégia de falha auditada.

**Aceite:** sem contagem → taxa indefinida; throughput não duplica retry; falhas entram no denominador; tempo até JSON válido disponível; relógios de hosts não são subtraídos entre si. Métricas regeneráveis a partir de brutos sanitizados.

### C11 — P0/P1 — Segurança, proxy e credenciais

**Fazer:** limitar tamanho de header/token e leitura de corpo (token é processado antes do limite de corpo); validar domínios não vazios e campos existentes ao provisionar. `requests_per_minute` deve ser finito/positivo. `write_credential_file()` escreve atomicamente, mas atualizações simultâneas podem perder usuários; validar arquivo inteiro antes/depois e serializar provisionamento. Revogação/rotação hoje exige restart do gateway; documentar ou implementar reload seguro. Não registrar segredo em CI nem colocá-lo em URL.

Tratar HTTPS por transporte real, não por header livre `X-Forwarded-Proto`. Uvicorn/proxy precisam ter configuração explícita de proxies confiáveis; testar spoof de forwarded headers em HTTP local. TLS interno para nós remotos e autenticação serviço-a-serviço/ACL de rede; token de usuário nunca é encaminhado ao runtime. Não expor API de inferência na Internet.

Pseudônimo de usuário muda a cada restart: decidir correlação por rodada ou HMAC com chave local estável, sem publicar chave. `/metrics` hoje exige autorização, `/health` é liveness e `/v1/domains` catálogo público; manter ausência de dados sensíveis e documentar readiness separada.

**Aceite:** 401/403/429/503 distintos, limites por usuário independentes, auto não burla domínio, rotação invalida token conforme política, certificado não confiável/hostname errado rejeitado, forwarded header não burla TLS. Captura autorizada de tráfego mostra cifragem sem chaves/prontuários no pacote de entrega.

### C12 — P1 — Configuração remota e reprodução

**Inspeção:** config de backend exige caminho de GGUF, threads, chave privada/certificado do nó e contexto de runtime. Nó remoto HTTPS exige arquivos privados que não pertencem ao gateway; CLI tenta usar hostname remoto como endereço de bind local. Não há hash obrigatório validado no startup, parâmetros de GPU, lock Python nem teste de ambiente novo.

**Fazer:** separar cadastro público dos nós e configuração privada do runtime (§4). Gateway não precisa do GGUF/llama-server nem de chave privada do nó. Validar URLs via parser (scheme, host, porta, userinfo), rejeitar limites inválidos e cert+HTTP inconsistentes. Distinguir contexto por slot de contexto total: verificar comportamento de `-c` com `-np>1` no build fixado. Separar CPU budget por processo, affinity e GPU (`n_gpu_layers` etc.) nos perfis LLM.

Fixar dependências Python transitivas, runtime/build, templates e arquivos de modelo. `devenv.lock` trava Nix, não resolve ranges Python do `pyproject.toml`. Corrigir detecção de alteração do pyproject no setup (scikit-learn foi duplicado em devenv para forçar atualização). Backend sem instalação llama.cpp; LLM sem sklearn/FastAPI desnecessários. Instalação/pacote tem que funcionar fora da raiz e com caminho de config documentado.

**Aceite:** gateway puro inicia com URLs remotas sem modelos locais; runtime inicia com config própria sem credenciais de usuários; clone limpo passa CI; modelos não são baixados por testes comuns.

### C13 — P1 — Roteador piloto não representa a tarefa real

**Inspeção:** split separa tópicos, mas reutiliza templates. Parte dos exemplos clínicos pede explicações/comparações, enquanto o domínio público só aceita documento a extrair. `load_examples()` obriga grupos com ambas as complexidades, não valida que grupo pertence a um único domínio, e pode rejeitar dataset com mais de dois domínios apesar de configuração genérica. Probabilidades arredondadas são usadas antes de comparar limiar.

**Fazer:** alinhar documentos/perguntas às entradas reais, separar famílias linguísticas/templates e grupos clínicos, incluir ruído, ambiguidade, input adversarial e fora de domínio. Rótulos com rubrica humana, dataset de teste escrito independentemente. Comparar valores não arredondados com limiar, avaliar calibração/confiança e fallback. Exportar IDs/split/hash, acurácia/matriz por classe, cobertura seletiva/fallback e overhead p50/p95. Treinar/fixar artefato offline; evitar avaliar e re-treinar em toda inicialização de produção. Não carregar artefatos pickle de origem não confiável.

Seleção de complexidade deve combinar tipo de tarefa, tamanho tokenizado e rótulos validados pelo custo/qualidade dos dois modelos. Pouca confiança → política conservadora declarada; fallback para maior não prova qualidade. Não ligar a política ao teste de qualidade sem registro de rodada.

**Aceite:** teste verdadeiramente independente, esquema do conjunto coerente, domínios explícitos inalterados, threshold/fallback medidos, pequeno versus maior avaliados contra rubrica, resultado não anunciado como 100% generalizável.

### C14 — P2 — Documentação e higiene

- Atualizar claims de M1/M2: código piloto/smoke não é conclusão dos marcos; vazão principal e roteiro ainda faltam.
- Simulado ignora `max_output_tokens` e não fornece tokenizer; melhorar fixtures para truncamento e budgets sem fingir tok/s real.
- Cliente tolerar JSON/HTTP não-JSON malformados, transport errors e seq/event inválidos, e emitir relatório de falha com tempos parciais.
- `.gitignore` atual cobre diretórios sensíveis; reforçar `.env`, `.env.*` com exceção de `.env.example` sanitizado, certificados/keystores, caches frontend e logs locais nos três repos. Não ignorar todo `data/`: exemplos autorais sintéticos e manifests sem restrição são rastreáveis.
- Histórico tem identidade `moinholigeiro <pc_ack>`; não reescrever commits nem inventar email. Configurar identidade local futura somente com dados confirmados do usuário.
- Scripts Bash do README podem não funcionar em zsh (`read -rsp`); oferecer script/login local compatível ou indicar shell. Não publicar token em argumento de curl/process list nas instruções operacionais preferidas; orientar leitura de arquivo restrito/config temporária ou client env.
- Licença do código do grupo/avisos de terceiros pendentes: propor e obter decisão, não atribuir uma por conta própria.

## 4. Arquitetura e responsabilidade dos três repositórios

Nomes **propostos**, não remotos já criados:

1. `UFES_Redes_Trab2_Frontend`
2. `UFES_Redes_Trab2_Backend`
3. `UFES_Redes_Trab2_LLM`

**Local obrigatório dos três repositórios:** criá-los como três diretórios irmãos, diretamente no diretório de trabalho que contém `Tudo Junto/` (isto é, ao lado de `Tudo Junto/`, não dentro dela):

```text
<diretório-de-trabalho>/
├── Tudo Junto/
├── UFES_Redes_Trab2_Frontend/
├── UFES_Redes_Trab2_Backend/
└── UFES_Redes_Trab2_LLM/
```

Os três destinos são repositórios independentes, cada qual com seu próprio `.git`; nenhum fica dentro de outro. O repositório Git atualmente aberto neste diretório é a origem dos arquivos/histórico a migrar, não substitui a criação do diretório `UFES_Redes_Trab2_Backend/`. Na etapa E0, definir e registrar como preservar o histórico do Backend na migração para esse destino, sem apagar ou reescrever a origem. Não inicializar os destinos nem mover arquivos durante esta revisão do plano. O nome `UFES_Redes_Trab2` solicitado anteriormente era para um remoto não criado; decidir aliases/nome final ao criar remotos, sem bloqueio para planejamento local.

```text
Frontend web / cliente Python / gerador de carga
           | HTTPS POST + SSE (API pública)
           v
Backend / gateway (um worker)
  auth -> limite -> domínio -> modelo -> pool compatível -> reserva de fila
  -> dispatcher por nó -> stream -> validação/métricas/resultado
           | HTTP/SSE interno controlado ou HTTPS + auth de serviço
           +----> llm-small-a (host A, modelo pequeno, 1 slot)
           +----> llm-small-b (host B ou mesmo host, réplica equivalente, 1 slot)
           +----> llm-large-a (modelo maior, 1 slot)
                        todos implantados a partir do repositório LLM
```

### 4.1 Frontend

**Responsável por:** apresentação, inputs/domínios, preview, estados, cancelamento, tempo observado no navegador e download válido. Nenhum peso/runtime/classificador, nenhuma decisão de balanceamento.

Stack sugerida, ainda não escolhida pelo usuário: TypeScript + Vite + React, testes Vitest e Playwright. Pode adaptar a stack, mas fixar lock, Node via devenv, acessibilidade e bundle pequeno. Sem SSR obrigatório, login corporativo, banco ou chat persistente.

Estrutura sugerida: `src/api/`, `src/features/generation/`, `src/components/`, `tests/`, `contracts/`, `devenv.*`, lock do gerenciador, README.

Requisitos do MVP:

- Login por token provisionado localmente. Estado em memória, não localStorage por padrão; nunca em query string, telemetry ou bundle. Limpar token/resultados ao sair.
- Formulário Redes, extração clínica e auto; entrada de texto e arquivo `.txt` UTF-8 limitado, aviso sintético/não clínico. Não inserir automaticamente os 500 registros no navegador.
- `fetch()` POST com header Authorization e stream `ReadableStream`. **EventSource nativo não suporta este POST com Bearer**; não trocar por token em URL.
- Parser SSE incremental com `TextDecoder` em modo streaming, fronteiras de UTF-8/CRLF/frame, comentários, múltiplas linhas data e evento terminal. Mostrar deltas sem esperar palavras/JSON completo.
- Estados: conexão, espera sem primeiro token, geração parcial, validação, concluído, cancelado, erro antes/depois de saída. `meta` pode chegar só com primeiro evento real; conexão/heartbeat não são TTFT.
- Para JSON, preview textual “não validado”; exportação só após `result` + `done`, nunca JSON reparado silenciosamente.
- Abortar via `AbortController`; retry manual abre resposta nova, sem colar prefixos e sem garantir mesma saída.
- Mostrar request ID, domínio/modelo/política resolvidos e TTFT/E2E/tempo até resultado. Usar `performance.now()`; separar medição no navegador dos tempos gateway/runtime.
- Tratar 401/403/422/429/503 com mensagens e Retry-After; auto incerto oferece domínio explícito.
- Painel administrativo mínimo de nós/filas apenas para token autorizado; não mostrar corpos, usuários ou prompts internos. Não é dashboard de benchmark inventado.
- Renderizar saída como texto escapado. Se Markdown, sanitizar HTML/links, bloquear XSS; CSP e ausência de scripts terceiros que recebam dados/token.
- Testes de browser com backend simulado: Unicode dividido, fila, 429, cancelamento, EOF, parcial, result sem done e logout.

Deploy: preferir mesma origem HTTPS com proxy encaminhando `/v1` e `/metrics` sem buffering. Se origem separada, CORS allowlist exata, headers/métodos explícitos, preflight e validação TLS do navegador pela CA em perfil local dedicado. Não usar wildcard com credenciais. Não instalar CA global sem autorização. Não mascarar erros de certificado com bypass do browser.

### 4.2 Backend

**Responsável por:** contratos públicos, auth/permissões/rate limit, roteador, prompts/schema, filas/aging, modelos elegíveis, load balance/failover, cancelamento, validation/export, métricas, clientes offline, experimentos e documentação acadêmica integrada.

Permanecem aqui: `api.py`, `gateway.py`, `scheduler.py`, `balancing.py`, `security.py`, `routing.py`, `protocol.py`, `jobs.py`, `metrics.py`, `prompts.py`, `clinical/`, adapters HTTP em `backends/`, cliente CLI, dataset autoral do roteador, testes e futuros `experiments/`/`evaluation/`.

**Importante:** `backends/llama_server.py` é adapter HTTP do gateway e fica no Backend. Não é o motor de inferência. O simulado de integração também fica nos testes do Backend.

Config backend deve ter `node_id`, URL, model_id/hash, capacidades domínio/schema/profile, slots declarados, trust CA e credencial de serviço opcional, health/pool/queue policy. Paths de GGUF, threads CPU de execução e chaves privadas do nó não ficam aqui. Default de domínio, prompt/schema e políticas de escolha são do backend.

O backend pode registrar metadados públicos do modelo para reproduzir a experiência, mas fonte autoritativa do arquivo/build é um manifesto versionado do LLM. Não depender de imports Python ou acesso ao filesystem de outro repo.

### 4.3 LLM — um repositório, N implantações

**Responsável por:** build/pin llama.cpp, downloads locais verificados, manifesto/model cards/licenças, configuração de bind/runtime, slots/threads/contexto/GPU, health/readiness/metadados, tokenizer e timings disponíveis, segurança de serviço interno e monitoramento do processo.

Estrutura sugerida: `models/manifest.json` (sem pesos), `configs/nodes/*.toml`, `scripts/download-models`, `scripts/start-node`, `scripts/verify-models`, `tests/`, `contracts/`, `devenv.*`, docs de CPU/remoto/GPU.

Migrar a parte `_runtime_argv`, start/hash/download de GGUF hoje em `cli.py`. Modelo real permanece `llama-server`; wrapper/supervisor leve somente se necessário a auth/metadados/observação. Não acrescentar outro broker ou fila grande. Um runtime por réplica com slots fixados, pesos residentes. Config independente aceita o mesmo código com `NODE_ID`, bind/port/model/threads diferentes.

Node nunca escolhe domínio/modelo global do usuário, não implementa RR e não recebe token de usuário; recebe chamada interna já resolvida. Deve rejeitar capacidade/modelo incompatível e proteger endpoint se rede não confiável. Prompts/schema chegam pelo backend; nenhuma cópia divergente de lógica clínica nos nós.

A CA pública/trust bundle pode existir nos clientes; chave privada só no host de destino. URL pública de nó e bind privado são campos distintos. Para nós remotos já protegidos por proxy, backend não exige certificado privado local. Autenticação interna pode usar credencial opaca diferente por serviço; mTLS opcional se escolhido, sem complicar MVP.

Contrato interno: manter `/v1/chat/completions` SSE compatível com o build fixado e `/health`; definir metadados versionados ou manifesto implantado para model hash/context/slots/template/runtime. Tokenização e timings podem usar endpoints nativos de llama.cpp se suportados, evitando nova implementação.

### 4.4 Contratos sem quarto repositório

- Fonte autoritativa da API pública e JSON Schema no Backend: `contracts/public/v1/`. DTOs/fixtures de `meta`, `delta`, `result`, `done`, `error` e HTTP errors. OpenAPI FastAPI precisa documentar também o stream e os limites, não só um POST sem schema útil.
- Fonte autoritativa do contrato do runtime e manifesto no LLM: `contracts/internal/v1/`.
- Frontend consome cópia/exportação ou pacote gerado da API pública, com versão/hash e script de sincronização; adapters Backend têm fixtures da versão interna. Evitar edições manuais divergentes.
- Pin de integração registra SHA/tag dos três repos, schema/prompt/runtime/model/data/config hashes. Não ler `main` flutuante de outro repo para resultados reproduzíveis.
- Versionar de forma aditiva; mudanças incompatíveis de evento/schema exigem versão e testes de compatibilidade. Não adicionar callbacks que dependem da estrutura interna de `Job` no frontend/LLM.

## 5. Migração segura de repositórios — checklist executável

1. Inventariar Git, alterações e arquivos ignorados; salvar manifesto de migração e hashes das fontes sem copiá-las. Registrar base `9371880` e commits posteriores.
2. Executar regressão atual (81 testes) e documentar ambiente. Fazer correções P0 no repo atual com testes focados antes de grande reorganização, ou migrar os módulos sem alteração de comportamento e corrigir imediatamente em seguida. Não misturar tudo num commit irrevisável.
3. Criar, ao lado de `Tudo Junto/` no diretório de trabalho, os três diretórios/repositórios independentes `UFES_Redes_Trab2_Frontend/`, `UFES_Redes_Trab2_Backend/` e `UFES_Redes_Trab2_LLM/`. O Backend também é um destino novo; migrar para ele preservando o histórico conforme estratégia definida em E0. Não copiar `.devenv`/pesos/dataset/segredos para outros repos; não apagar originais. Garantir que cada `.git` pertença a um dos três destinos e não fique aninhado dentro de outro repositório de produto.
4. Extrair runtime para LLM por cópia controlada dos arquivos pertinentes, fixtures e novo pyproject/CLI se necessário. Atualizar dependências do backend: sem `llama-cpp` obrigatório no ambiente de produção/backend e sem startup local de runtime no comando gateway.
5. Dividir config: arquivos Backend declaram pools; arquivos LLM declaram execução. Migrar cada perfil atual com tabela de correspondência, sem alterar silently o modelo padrão e a fila. Expor aliases de compatibilidade só temporariamente e documentar retirada.
6. Fixtures de contrato e teste gateway remoto sem GGUF têm de passar antes de remover a antiga CLI runtime. O pacote node tem smoke independente com modelos opcionais e checks hash obrigatórios.
7. Frontend inicial usa backend simulado via protocolo real; CI do Frontend não precisa de GGUF nem dataset clínico. E2E tri-repo usa clones/refs explicitamente fixados.
8. Preservar `data/anonymedbr/` neste local ou mover apenas após instrução inequívoca; adapter usa path externo configurável. Nenhum teste normal exige material restrito. Não criar quarto repositório de dados nem versionar derivados restritos por acidente.
9. Criar READMEs próprios e guia de integração no Backend. Ambiente declarativo próprio por repo; scripts de integração no Backend referenciam caminhos/URLs configuráveis, sem inventar root monorepo.
10. Commits pequenos por etapa, revisão de `git diff --cached`/segredos/arquivos grandes antes de commit. Não fazer push até solicitado. Não reescrever história existente.

**Definição de pronto da divisão:** cada clone tem teste/build próprio; Backend roda sem pesos/llama-server local; LLM roda sem sklearn/gateway; Frontend acessa só Backend; N nós implantados do único LLM são balanceados pelo Backend; integração tem versões registradas e resultados reproduzíveis.

## 6. Viabilidade dos modelos e recursos

- Confirmar origem oficial/model card, licença, revisão do GGUF, tamanho/hash, template e build. Os hashes existem nas configs atuais, mas strings de licença não substituem documentação primária registrada.
- Medir um candidato de cada vez em 10–20 documentos/prompts de desenvolvimento, sem exigir GPU nem benchmarkar todas as variantes.
- Tokenizar prompt completo + documento + reserva de saída pelo tokenizer correto. Caracteres ≠ tokens. Definir rejeição `context_exceeded` em vez de truncar silenciosamente documentos.
- Registrar RAM/PSS/RSS/mmap, swap, CPU/threads, thermal/throttling, prefill/decode, slots e KV cache. Somar RSS de réplicas não mede memória física exclusiva. Aceitar resultado CPU lento.
- Perfis: mínimo dois modelos/domínios; réplica pequeno+pequeno com maior disponível; hosts distintos preferidos. Se tudo não couber em 8 GB, nós remotos ou modelos menores validados/fallback do plano original, não nós fictícios.
- Perfil 3 runtimes atual usa 4 threads cada: em alvo de 4 núcleos isso supercompartilha CPU. Fazer perfis budgetados (ex.: threads distribuídas) e controlar CPU total na comparação.
- Desligar reasoning via configuração/template suportado, testar reasoning_content e consumo de tokens não visíveis. Não confundir tokens internos/reportados com deltas visíveis.
- Comparar geração compacta de JSON versus pretty sem alterar semântica; budgets suficientes por classe. Não impor 128 tokens a todos os prontuários.
- GPU futura por config e documentação (camadas offload/context/VRAM); testar somente quando disponível, sem alterar baseline CPU.

## 7. Extração, dados, revisão e exportação

### 7.1 Integridade e permissões

Escrever adapter local read-only: pareamento por `annotation.source.source_record_id == source.id`, IDs únicos, synthetic e checksums de registros/fontes/provenance. Só canônicos `processed/reviewed/`; não agregar wrong-source nem archived. Auditorias de lote apenas quando há dúvida concreta.

A pendência de licença bloqueia redistribuição e pode limitar uso; verificar direitos antes das rodadas com o dataset e registrar decisão. **Não bloquear a implementação do adapter/testes sintéticos, a revisão arquitetural ou M1 por isso.** Enquanto não esclarecido, testar com casos autorais e manter material existente privado/local, sem enviá-lo a APIs. O README atual é conservador, mas não usar licença como justificativa para omitir ferramentas F3.

### 7.2 Split e amostra humana

- Detectar idênticos/quase duplicados e famílias de templates; grupos antes de split, com normalização conservadora para detectar duplicatas, sem modificar fonte.
- Meta de 100 desenvolvimento/400 avaliação preliminar, seed/IDs/grupos registrados; grupos podem tornar contagem exata impossível, documentar sem vazar família só para bater número.
- Selecionar 60 da avaliação para revisão humana estratificada por ausência/presença, negações, medicamentos, sinais vitais e tamanho. Dois revisores e adjudicação; não fingir que são profissionais de saúde.
- Referência existente é gerada/revisada por LLM, não adjudicação humana independente. Comparar fidelidade ao texto, não veracidade dos cenários.
- Congelar modelo/prompt/schema/política antes de olhar teste; mudanças depois são rodada nova com ID.

### 7.3 Qualidade e regressão

Medir JSON/schema válido, truncamento, coerção rejeitada, hallucination em campo ausente, idade/sexo explícitos, entidades e atributos (nome+dose+via+frequência), negação/hipótese/histórico e unidades. Normalização predefinida e explícita; não remover dose nem tolerar automaticamente idade ±1/PA ±10 para aumentar score. Queixa usa rubrica humana ou correspondência limitada, não somente igualdade literal. Separar métricas presente/ausente, referência LLM e subconjunto humano.

Criar fixtures autorais dos erros conhecidos: medicamento único não pode gerar diagnóstico/queixa de pneumonia; hipótese de bronquite não vira confirmação. Não realizar segunda chamada silenciosa para reparar ou validar por LLM; se modo de repair surgir no futuro, versão/custo/tempo próprio.

### 7.4 Cliente de lote e exportação

- Lote chama **a mesma API gateway**, autenticação/TLS/filas; nunca inference direto para medir serviço.
- JSON/JSONL canônicos com source/request/run ID, versão/hash/policy, status e métricas externas ao objeto clínico; checkpoint/resume por ID e perfil congelado, não por ordem de linha. Falhas preservadas para reexecução explícita.
- Retomada não duplica saídas nem reutiliza resultado de prompt/modelo diferente. Limite assíncrono configurável e atomicidade do checkpoint.
- CSV determinístico por tabela pacientes, diagnósticos, medicamentos e vitais, IDs relacionais. Escapar células que planilhas interpretam como fórmula, preservar original JSON, encoding/unidades/null documentados. Não juntar arrays com vírgulas ambíguas.
- Frontend só baixa resultado validado concluído; FHIR/CID/SNOMED/OCR/RAG/diagnóstico automático fora do MVP.

## 8. Filas: FIFO versus prioridade não preemptiva com aging

Implementar estrutura auditável com sequence ID, enqueue, deadline, estimate/class e transições. FIFO estável é baseline. Prioridade usa custo previsto antes da geração (budget/tokens de entrada/tipo calibrado), não output real conhecido depois. Valor de complexidade linguística não é automaticamente tempo de serviço.

Aging: definir regra determinística e parâmetro, por exemplo promover longos que cruzam limite de espera definido no piloto; recomputar prioridade ao despacho para não deixar heap com prioridades obsoletas. Registrar promoções/starvation e impacto nos longos. Sem preempção de runtime.

Retries/reroute preservam idade lógica e ordem de justiça conforme política registrada, não ganham juventude artificial nem prioridade ilimitada. Cancelamento remove pendente e libera recursos. Reserva atômica continua sendo propriedade do backend single-worker.

Testes: empates, ordem FIFO, pequenos chegam após longo ativo (não preemptam), aging sob fluxo contínuo, limite de ativos, queda/cancelamento/expiração com prioridade e capacidade. Simulação discreta utiliza a mesma definição da política real, sem inferência.

## 9. Experimento completo e evidências de entrega

### 9.1 Ferramentas a implementar no Backend

`experiments/calibrate`, `predict`, `closed_load`, `run_matrix`, `analyze`, `plot`, `fault_scenarios` (nomes ilustrativos). Client assíncrono reutiliza conexões HTTP e parser SSE real; HTTP/TLS keep-alive da carga não deve ficar diferente da medição documentada. Frontend não é gerador obrigatório de carga.

Config de rodada: domínio/modelo/pool fixos, hashes, N, ciclos/duração, warmup, seed, policy, mixed classes, orçamento de tokens, deadlines, TLS, rate limit alto, resource budget e critérios de invalidação. IDs run/repetition/client/request únicos.

Guardar brutos JSONL/CSV + config + calibragem + previsão em novos artifacts locais. Publicar apenas resultados sanitizados permitidos; não ignorar para sempre todas as evidências reprodutíveis: pacote selecionado sanitizado com hashes pode ser commitado em docs/results após revisão. Nunca incluir token/textos restritos/CA privada.

### 9.2 Hipóteses e previsão anterior

H1: capacidade fixa satura vazão; aumentar população fechada aumenta espera/TTFT, sem fila infinita. H2: prioridade reduz tempo dos curtos e pode piorar longos; aging limita starvation. H3: réplicas no mesmo host redistribuem trabalho sem criar CPU/RAM.

Calibrar 10–20 prompts fora do teste de qualidade, um ativo, medir distribuições P (prefill), S (serviço), output tokens e transporte. Aquecer por requisições concluídas. Escolher budgets/ciclos após piloto; meta aproximadamente dez conclusões por cliente/repetição, com redução explicitada quando CPU impuser limite.

Baseline serial fechado, um nó/slot, think time zero:

```text
X_requests(N) ≈ 1 / E[S] quando ocupado continuamente
TTFT(N) ≈ (N - 1) * E[S] + E[P] + transporte
R(N) ≈ N * E[S] + transporte
```

Não usar Erlang-C aberto como se fosse modelo fechado. Para réplicas/classes/prioridade, simulação discreta com distribuições da calibração, sem usar a medição principal para ajustar a própria previsão. Salvar previsão/config/hash com timestamp e commit antes da rodada, sem segredos. Limiar operacional de TTFT predefinido, mesmo se crescimento gradual começar em N=2.

### 9.3 Matrizes

| Matriz | Execução mínima |
| --- | --- |
| A — Obrigatória | N=1,2,4,8,16, um nó/slot, modelo/domínio explícito fixos, FIFO, cinco repetições independentes |
| B — Pergunta-desafio | Mesma população e mistura fixa curto/longo, FIFO × prioridade com aging, métricas por classe/total e justiça dos longos |
| C — Desempenho | Duas ou mais réplicas equivalentes, RR × menor fila × menor latência, recursos fixos, cinco repetições em N representativos; ideal todos N |
| D — Falhas | Antes do primeiro delta e durante geração, repetições; request ID, destino, retry, bytes/tokens perdidos, validade e recuperação |
| E — Segurança/Inteligência | Casos auth/TLS e avaliação de domínio/complexidade/qualidade/custo separados da carga principal |

TLS ligado na matriz principal, tokens de carga autorizados com limite alto. Auto/desempenho de modelos distintos não se mistura com A/B/C. Runtimes mantêm pesos residentes. Cache de resposta desligado; prefix/KV cache controlado/documentado, não confundir aquecimento com ganho real de balanceamento.

Randomizar ordem de rodadas, drenar filas e isolar contadores/run IDs sem apagar história. Registrar carga externa, CPU/RAM/PSS/swap, temperatura/throttling e consumo do gerador; preferir cliente em outro host. Não invalidar rodada só porque saturação ficou lenta. Timeout/rejeição tem taxa e censura, TTFT de sucesso sozinho é enviesado.

Para throughput em intervalo, escolher janela e método de contagem explícitos. Rodada por ciclos com início/fim e streams completamente drenados simplifica contagem final de tokens úteis; em janela fixa, usage final não atribui sozinho tokens à janela. Tratar streams parciais/falta de contagem separadamente e não usar SSE-count como tokens.

### 9.4 Análise/gráficos

1. TTFT cliente × N: previsto/observado, p50/p95 por repetição, IC95% entre repetições e erros/censura.
2. Vazão agregada tokens/s × N e requisições/s complementar.
3. Decomposição fila/prefill/decode/serviço/transporte, tempo até `result` válido e tokens/s individuais.
4. FIFO × prioridade: curtos/longos, E2E, espera/aging/starvation, não apenas média global.
5. Balanceadores: distribuição entre nós, queue depth, equidade/capacidade e falhas em tabela/timeline.

IC baseado em repetições, não em tokens correlacionados. Ressalvar p95 com poucas amostras. Discussão: conversar depende de início percebido e fluidez; JSON pode ter TTFT de `{` sem valor útil até `result`. Não concluir preferência humana sem estudo nem métrica universalmente superior.

## 10. Plano por dependências e marcos intermediários

| Etapa | Tarefas | Depende de | Saída/aceite |
| --- | --- | --- | --- |
| E0 | Inventário, regressão, ADRs dos três repos e contratos | Estado atual | Baseline e lista de pendências; nada perdido |
| E1 | C01–C06, deadline/falhas/cancelamento/backpressure | E0 | Testes de bugs e fluxo terminal robusto |
| E2 | Divisão local Backend/LLM, config pública/privada e dependências | E0/E1 | Implantação independente, gateway sem pesos locais |
| E3 | C07–C13, métricas corretas, auth/proxy/compatibilidade/router | E1/E2 | Baseline explícito fixo e metrologia auditável |
| E4 | Frontend mínimo e contrato público/E2E | E2/contrato E3 | Browser SSE seguro/cancelável, sem exportação parcial |
| E5 | Runtime/modelos/perfis 8GB/remoto, quality fixtures e F3 ferramentas | E2/E3 | Viabilidade registrada; direitos/dataset tratados sem publicação |
| E6 | FIFO/prioridade/aging + closed-load + simulação | E1/E3 | Políticas e carga testadas sem GGUF nos testes unitários |
| E7 | Piloto/calibração, freeze, previsão e matriz | E5/E6 | Roteiro M2 executável, previsão anterior salva |
| E8 | Rodadas reais A–E, revisão humana permitida e análises | E7 | Brutos, erros, repetições, gráficos, qualidade/custo |
| E9 | READMEs/integração/relatório/demos e clone limpo | E4/E8 | M3 com evidências reproduzíveis e ≤6 páginas |

Prioridade de esforço: correções de integridade → fronteiras/config → métricas → carga/filas → frontend pequeno → medições. E4/E5 podem avançar de forma independente após contratos, mas nenhum agente deve editar mesma interface sem coordenação. Sugestão para trio: A=Backend/filas, B=LLM/qualidade, C=Frontend/clientes/experimento; revisão cruzada necessária.

## 11. Testes, CI e entrega reproduzível

- Backend: pytest unitário/HTTP, fixtures malformadas, segurança, roteador, scheduler, simulation/load; lint/format, type checking incremental se adotado.
- LLM: comandos/config/manifest/hash/trust; integração real opt-in com path do modelo, sem baixar GBs em cada CI.
- Frontend: typecheck/build, parser SSE, componente/state/XSS, E2E com backend simulado. Novo frontend não substitui cliente CLI científico.
- Integração tri-repo: refs fixos, gateway + dois nós reais quando recursos permitem; smoke simulado claramente rotulado em CI comum; teste de queda por PID/processo conhecido, não `pkill -f` amplo.
- Testar CA incorreta/SAN errado e TLS real; capturas sanitizadas sob autorização. Nunca colocar private key em artifacts publicados.
- Contratos teste/compatibilidade dos dois lados, including versões de schema. Documentação não deve ficar dizendo 81 testes para sempre: atualizar números conforme real.
- Ambiente fresh devenv/venv reproducível, sem pip global, pesos/dados ignorados, scripts idempotentes com falha limpa e não destrutiva.
- Docs no Backend: arquitetura dos três repos, portas/URLs, prerequisites, startup CPU/remoto/GPU, gerar confiança/token, rodar falhas, calibrar/prever/medir/analisar, licenças e troubleshooting.
- Relatório ≤6 páginas: objetivo/arquitetura e topologia; hipóteses/metodologia; figuras/erros; políticas de fila/load balance; segurança/inteligência/qualidade; desafio/limites. Autorização do trio registrada.
- Demos: M1 de cinco minutos com dois domínios e fila; M2 com token 401/403/429/TLS, auto, réplicas e falha; final com gráficos reais. Não reiniciar modelos a cada request.

## 12. Não expandir escopo sem necessidade

Fora do MVP: fine-tuning, OCR/PDF, FHIR, RAG, cache semântico, integração hospitalar, diagnóstico automático, grande painel, cadastro corporativo, múltiplos workers gateway, Kubernetes/service mesh, benchmark de todas as variantes/GPU e revisão humana de 500 documentos.

Não cortar: dois domínios/modelos de baseline distintos, filas e métricas corretas, duas réplicas reais equivalentes na prova de load balancing, token+autorização+rate limit+TLS, roteamento semântico avaliado, erro mid-stream, prioridade/aging, carga fechada N exatos, previsão prévia, repetições/gráficos e os três repositórios solicitados.

## 13. Instrução pronta para o próximo agente

> Leia `PLANO_CONTINUIDADE_REVISAO_E_3_REPOS.md`, o plano original e o enunciado. Confira Git e baseline; a revisão em `9371880` passou 81 testes, mas confirmou EOF sem [DONE] aceito, chunk malformado com exceção e coerção clínica indevida. Corrija integridade/deadlines/cancelamento antes de medir. Crie os três repositórios independentes diretamente no diretório de trabalho, ao lado de `Tudo Junto/`: `UFES_Redes_Trab2_Frontend/`, `UFES_Redes_Trab2_Backend/` e `UFES_Redes_Trab2_LLM/`. O Backend é um destino novo para migrar, com estratégia de preservação do histórico definida em E0; não trate o repositório de origem como substituto desse diretório. Não confunda o adapter HTTP em backends/ com o motor LLM. Preserve história e arquivos restritos; não publique nem mova dataset/pesos/segredos sem autorização. Backend roda com URLs remotas sem GGUF/keys dos nós; LLM tem build/model/runtime config próprios; Frontend usa HTTPS POST SSE via fetch, sem escolher nós nem exportar JSON parcial. Mantenha domínio explícito/modelo fixo para baseline, auto como rodada adaptativa separada. Complete métricas reais, priority/aging, client de lote/avaliação, carga fechada, previsão antes de medir e matrizes com repetições/gráficos. Use apenas devenv/Nix/venv local. Faça etapas pequenas, testes de aceite e commits locais quando autorizados, atualize docs com evidências e não chame piloto/smoke de entrega ou benchmark completo.

### Checklist final do handoff

- [ ] Bugs confirmados têm regressão que falha antes e passa depois da correção.
- [ ] Requisição/stream tem finalização única; EOF, erros e cancelamento nunca parecem sucesso.
- [ ] Backend único dono das filas/load balance; vários nós implantados do único repo LLM.
- [ ] Três repos independentes e contratos sincronizados/pinados, sem quarto repo obrigatório.
- [ ] Backend não exige arquivos GGUF/chaves privadas de nós remotos.
- [ ] Domínio explícito é estável; auto não burla permissão e tem avaliação independente.
- [ ] Tok/s nunca significa chunks/s; métricas incluem tentativas, erros e tempo até resultado.
- [ ] Frontend preview/export/cancel/retry/TLS seguros, sem token persistente desnecessário.
- [ ] FIFO/prioridade com aging e recursos reais equivalentes estão testados/medidos.
- [ ] Dados canônicos preservados, permissões registradas, amostra humana honesta e splits sem vazamento.
- [ ] Carga N=1/2/4/8/16, previsão congelada anterior, cinco repetições e gráficos reais.
- [ ] READMEs, relatório até seis páginas, demos e reprodução com refs dos três repos.
