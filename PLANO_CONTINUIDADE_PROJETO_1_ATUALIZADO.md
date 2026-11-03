# Projeto 1 — Plano detalhado de continuidade e instruções para agentes

**Data da revisão:** 02/11/2026.  
**Base:** enunciado, plano inicial e snapshot local das três pastas, incluindo alterações ainda não commitadas.  
**Finalidade:** orientar a continuação do trabalho existente, não iniciar outra implementação nem declarar o projeto entregue.

## 1. Leia isto primeiro

O produto é o **Projeto 1 — Gateway distribuído de LLMs abertos**, apesar de os diretórios se chamarem `Trab2`. Não é o Projeto 2 de transmissão de áudio.

Este documento é o roteiro operacional atualizado. Preserve os documentos anteriores como histórico:

1. `Propostas de Trabalho.md`: fonte normativa acadêmica, sobretudo Projeto 1, marcos e avaliação. Esclarecimentos do professor prevalecem.
2. `PLANO_COMPLETO_PROJETO_1.md`: decisões iniciais do grupo, anteriores à implementação. Sua descrição de “estado atual” não corresponde mais ao código.
3. `UFES_Redes_Trab2_Backend/PLANO_CONTINUIDADE_REVISAO_E_3_REPOS.md`: revisão intermediária com problemas C01–C14 e proposta de separação. Algumas correções já existem; a separação física e o frontend já existem. Não executar novamente a migração descrita nele.
4. **Este arquivo:** diagnóstico do snapshot observado, pendências remanescentes, ordem de execução, testes e critérios de aceite.

As cópias do enunciado e do plano inicial dentro do Backend são idênticas às da raiz nesta revisão. Evite criar cópias divergentes de planos. Futuras atualizações devem registrar data, evidências e estado, não apagar o histórico.

### Decisões e restrições que continuam válidas

- Trio autorizado pelo professor, conforme o plano inicial. Não reabrir essa decisão; documentá-la na entrega.
- Inferência local com pesos abertos e `llama.cpp/llama-server`. Nada de API externa como fallback, treinamento obrigatório ou reimplementação do motor.
- Python para gateway/clientes/ferramentas. O frontend existente é **JavaScript nativo**, sem framework; preservá-lo. TypeScript/React/Vite eram sugestões, não obrigação.
- Três produtos independentes: Backend, Frontend e LLM. Um repositório LLM pode implantar vários processos/modelos/hosts.
- Backend é o único dono das filas, balanceamento, retries, autorização, roteamento e validação clínica. Frontend só usa a API pública; nó LLM não vira outro gateway.
- Alvo de reprodução: Ubuntu, aproximadamente **8 GB RAM, 4 núcleos, sem GPU**. GPU de aproximadamente 16 GB VRAM é futura e opcional.
- Ambiente declarativo Nix/devenv ou venv local; não instalar globalmente nem alterar `/etc` ou confiança global de certificados por iniciativa própria.
- Carga principal **fechada**: cada cliente espera a resposta/erro antes de enviar outra solicitação; N=1,2,4,8,16.
- Um incremento em **cada** trilha: Desempenho, Segurança e Inteligência. Não trocar por outros incrementos sem decisão do grupo.
- Extração clínica é caso de uso acadêmico de textos sintéticos, não diagnóstico, recomendação ou produto validado para saúde.
- Preservar dados, pesos, auditorias, alterações locais e histórico Git. Não publicar, fazer push, mover dados ou recriar remotos por efeito colateral.
- Licenças de código do grupo, dados e redistribuição de modelos precisam de registro/decisão; citação não substitui licença.

## 2. Snapshot e evidências desta revisão

### 2.1 Estrutura e Git

```text
Projeto_Redes_de_Computadores/                 # raiz de coordenação; não é repositório Git
├── Propostas de Trabalho.md
├── PLANO_COMPLETO_PROJETO_1.md
├── PLANO_CONTINUIDADE_PROJETO_1_ATUALIZADO.md   # este documento
├── UFES_Redes_Trab2_Backend/                   # .git próprio
├── UFES_Redes_Trab2_Frontend/                  # .git próprio
└── UFES_Redes_Trab2_LLM/                       # .git próprio
```

| Produto | HEAD observado | Estado |
| --- | --- | --- |
| Backend | `c54e055807387119e0e2edc6ecc8576dc58e2862` | Alterações locais preexistentes em README, configs, pyproject, API/config e testes |
| Frontend | `32a214ae44ffc9ba099620e64fbd0fa300ccafce` | Alterações locais preexistentes em README, HTML, controller, main e testes |
| LLM | `9e7ed5dabb96886f8b7e853c7d2a763160e56db4` | Alterações locais preexistentes em README, configs, node.py e testes |

**Os três já têm remoto chamado `origin`.** Os textos históricos “sem remotos”, “sem frontend”, “dados apenas em Tudo Junto” não descrevem este snapshot. Não se inferiu o estado de publicação remota e não houve acesso remoto nesta revisão. `Tudo Junto/` não está na raiz observada.

Como há modificações não commitadas, os HEADs acima **não identificam integralmente** a implementação analisada. Próximos agentes devem ler `git status --short` e `git diff` em cada pasta antes de editar. Não resetar, sobrescrever ou commitar todo o trabalho alheio indiscriminadamente.

### 2.2 Validações executadas

| Validação | Resultado desta revisão | Limite da evidência |
| --- | --- | --- |
| Backend, `devenv shell -- python -m pytest -q -p no:cacheprovider --basetemp=/tmp/opencode/projeto-redes-pytest` | **103 passaram** | Inferência simulada/MockTransport e HTTP/TLS local; não benchmark com GGUF |
| Backend, `ruff check src tests` e `ruff format --check src tests` pelo venv existente | Passaram; 31 arquivos formatados | Não prova correção de protocolos/experimentos |
| Frontend, `npm test` | **7 passaram** | Node e fetch simulado; não browser real/E2E |
| LLM, `python3 -m unittest discover -s tests -v` | **5 passaram** | Fixtures pequenas de arquivo/config/argv; não inferência real |
| LLM, `./scripts/verify-models` | Os dois GGUF conferem com o manifesto | Integridade de arquivo, não qualidade/licença/viabilidade |
| Dados canônicos | 500 fontes/500 anotações; IDs únicos e pareáveis; fontes `synthetic=true`; hashes de records, sources e provenance conferem | Consistência estrutural, não adjudicação humana |

Uma execução inicial do pytest diretamente pelo venv, fora do `devenv shell`, passou 102 testes e falhou no teste TLS por ausência de `openssl` no PATH (saída 127). No ambiente declarado os 103 passaram. **Não “corrigir” isso removendo o teste TLS ou instalando OpenSSL globalmente.**

Não se iniciou runtime real, não se repetiram smokes de inferência, não se executou benchmark nem revisão clínica humana nesta tarefa. `dist/` foi inventariado como saída gerada; não substitui teste de build fresco. Caches, ambientes, dependências instaladas, binários e cópias em `build/` não são fonte autoritativa a editar.

### 2.3 Material existente e sua interpretação

- `Backend/artifacts/logs/requests.jsonl`: 16 linhas (6 `done`, 9 `failed`, 1 `cancelled`), sem `run_id`; são evidências históricas de smoke, não matriz experimental.
- Logs dos três runtimes registram inicialização **HTTP**, quatro threads por processo e aviso de depreciação de `enable_thinking` por template. Não representam os novos perfis HTTPS nem comprovam execução após todas as mudanças.
- `Backend/experiments/` e `Backend/evaluation/` contêm **somente README de pendências**. Não existem carga fechada, previsão, análise, gráficos ou pipeline de avaliação implementados.
- `Backend/data/routing_examples.jsonl`: 120 exemplos autorais sintéticos gerados por templates; o split por tópico não impede compartilhamento de forma linguística.
- `Backend/data/anonymedbr/`: contém efetivamente raw, fontes/anotações consolidadas, manifestos, proveniência, lotes revisados e auditorias históricas. O README curto dessa pasta diz que os arquivos não estão ali, mas eles **estão localmente presentes**. Corrigir a documentação, não remover dados para fazê-la parecer verdadeira.
- Raw: treino 1.175 registros, validação 413, teste 299; os rótulos originais são de anonimização/NER e não um gabarito clínico de extração.
- Canônicos de extração: `processed/reviewed/`, IDs 875–1374, 500 pares. Comprimento dos textos: mínimo 537, média 1.953,812, máximo 4.170 caracteres; caracteres não são tokens.
- Auditorias têm correções de fontes/lotes e decisões sobre campos. `wrong-source`, versões duplicadas e `audits/archived/` não entram no dataset consolidado. Não aplicar conclusões antigas de proveniência sobre um snapshot anterior como se anulassem a consolidação corrigida.

## 3. Mapa do código: reutilizar, não reescrever

Todos os caminhos desta seção são relativos à pasta de cada produto.

### Backend — `UFES_Redes_Trab2_Backend/`

| Caminhos | Papel existente | Continuidade |
| --- | --- | --- |
| `src/llm_gateway/api.py` | FastAPI, autenticação/admissão, CORS, health, métricas, SSE público, probes | Corrigir readiness/deadline/terminal, instrumentar recepção e envio |
| `gateway.py`, `scheduler.py`, `jobs.py` | Seleção, reserva atômica single-worker, deque FIFO, estados, cancelamento/retry | Endurecer transições; acrescentar prioridade/aging sem perder FIFO |
| `balancing.py`, `metrics.py` | RR, ativos+pendentes, EWMA por nó, contadores/log JSONL síncrono | Pools comparáveis, exploração e registros de tentativa/requisição |
| `backends/base.py`, `backends/llama_server.py` | Adapter HTTP interno, schema, SSE/usage/finish | Fica no Backend; completar parser/limites/timings/cancelamento |
| `backends/simulated.py` | Simulado para testes, deltas por fragmentos/palavras | Melhorar fixtures, nunca usar como resultado obrigatório de LLM |
| `protocol.py`, `contracts/public/v1/` | DTO da requisição, encoder/parser SSE e schema de payloads | Contrato completo, fixtures, sync e validação dos clientes |
| `clinical/schema.py`, `prompts.py` | Schema v1, idade StrictInt, prompt clínico e de Redes | Preservar versões; fidelidade/semântica ainda não avaliadas |
| `security.py`, `cli.py` | Hash/token, autorização, bucket, serve/check-config/token-create | Hardening, provisionamento concorrente, proxy/trust e docs |
| `routing.py`, `scripts/build_routing_dataset.py` | TF-IDF+regressão logística de domínio/complexidade | Dataset independente, treinamento offline e custo/qualidade |
| `client.py` | Cliente síncrono, preview e relatório, result exige done | Base de semântica; acrescentar cliente assíncrono compartilhado |
| `configs/cpu_minimal.toml`, `m2_secure.toml`, `m2_replicas.toml` | Dois domínios/modelos, segurança e réplica pequena | Alinhar protocolos/CA/recursos; criar perfis experimentais fixos |
| `tests/`, `devenv.*`, `pyproject.toml` | Regressão/ambiente/pacote editável | Novos testes de defeitos e reprodução em ambiente limpo |
| `ADR-REPOS.md`, `MIGRATION_E0.md`, planos/README | Fronteiras e histórico de execução | Atualizar claims atuais mantendo registros históricos |

### Frontend — `UFES_Redes_Trab2_Frontend/`

- `index.html`, `src/main.js`, `src/style.css`: formulário com domínio/texto/arquivo/token, preview escapado, cancel/retry/logout/download.
- `src/api/sse.js`: parser incremental com UTF-8, CRLF dividido, comentários e múltiplas linhas data; hoje emite também frame incompleto ao EOF.
- `src/features/generation/controller.js`: fetch POST+Bearer, estados, validação da URL/trust e conclusão; ainda valida pouco os eventos e mede “TTFT” em meta.
- `tests/sse.test.js`, `tests/controller.test.js`: sete testes Node; faltam regressões de terminal, concorrência/logout e browser.
- `scripts/build.mjs`: copia HTML/src para `dist/`, sem bundler. `package.json` não tem dependências; ausência de lock não significa por si só instalação não reprodutível de pacotes inexistentes. Fixar Node e adicionar lock se forem introduzidas dependências.
- `contracts/public/v1/`: cópia atualmente idêntica à do Backend, ainda sem verificação automatizada de sincronização.

### LLM — `UFES_Redes_Trab2_LLM/`

- `scripts/node.py`, `start-node`: validam arquivo/hash e iniciam **uma** réplica por `exec`; não são serviço de readiness/supervisor completo.
- `scripts/download-models`, `verify-models`, `models/manifest.json`: URLs/revisões/hashes fixos; dois pesos já presentes localmente.
- `configs/qwen3-small.toml`, `qwen3-small-replica.toml`, `qwen35-large.toml`: portas 8101/8103/8102, um slot, CPU, HTTPS com arquivos privados não provisionados pelo script de CA do gateway.
- `contracts/internal/v1/runtime.md`: exige finish+[DONE]; readiness/modelo/hash/template/slots ainda descritos como futuros.
- `devenv.*`: `pkgs.llama-cpp` fixado indiretamente por nixpkgs; registrar versão/build efetivamente usados, não apenas “llama.cpp instalado”.
- `tests/test_node.py`: cinco testes unittest sem pesos reais; pyproject não fornece suíte de runtime/observabilidade.

## 4. Requisitos acadêmicos e estado conservador

| Requisito | O que já existe | O que falta para entregar |
| --- | --- | --- |
| Cliente → gateway → nós, streaming progressivo | SSE e adapters, CLI e cliente web | Integração atual real, protocolo completo, terminal/cancelamento/backpressure comprovados |
| Dois domínios com modelo/prompt/parâmetros próprios | Redes → Qwen3 1.7B; prontuário → Qwen3.5 4B; explícito usa padrão | Demonstração atual e registro de contexto/recursos/versões |
| Fila por nó e limite de concorrência | Deque FIFO, max_inflight/max_queue, cancel/expiração | Estado em falha/readiness, prioridade comparativa e fim coerente |
| TTFT, tokens/s, E2E e vazão | TTFT/serviço e usage parcialmente instrumentados | Tempos completos, agregado, resultado utilizável e tentativas/erros |
| Desempenho | RR/least_loaded/least_latency e retry antes de delta | Réplicas realmente compatíveis, comparação controlada e falhas repetidas |
| Segurança | Token+autorização+bucket+TLS/CORS/testes | Proxy spoof, limites/provisionamento, confiança interna e evidência cifrada |
| Inteligência | Classificador de domínio/complexidade piloto, auto | Holdout independente, input real, confiança e qualidade/custo pequeno/maior |
| Experimento obrigatório | Só plano/README | Calibração, previsão anterior, carga fechada N exatos, repetições e gráficos |
| Pergunta-desafio | Hipóteses e métricas propostas | FIFO × prioridade com aging; discussão TTFT/fluidez/JSON apoiada nos dados |
| Entrega | Documentação histórica e testes | READMEs de integração, demos M1/M2/M3, relatório ≤6 páginas e pacote reproduzível |

Pesos: núcleo 30%, incrementos 25%, experimento 25%, desafio 10%, organização/reprodução/apresentação 10%. Integração entre projetos é bônus opcional, não caminho crítico.

**Não marcar M1/M2 como entregues só porque os testes passam.** M1 exige demonstração de cinco minutos e as quatro métricas; M2 exige incrementos e roteiro experimental; M3 exige resultados, relatório e demo.

## 5. O que já foi corrigido em relação à revisão intermediária

Não reaplicar os antigos C01–C14 cegamente:

- Adapter já rejeita EOF sem `[DONE]`/finish, vários formatos malformados e certos dados após a terminação; há testes de regressão.
- Scheduler já tem barreira final contra `Exception`, byte count de saída e registro de deltas descartados do buffer.
- Pendentes já expiram por deadline total **ou** queue timeout; a API inicia prazo antes de ler/classificar o corpo.
- `completion_tokens` desconhecido já é `null`, `tokens_source=unknown`; não há mais fallback de contagem de deltas anunciado como tokens no scheduler.
- `idade` já usa `StrictInt`; boolean/string são rejeitados em regressão.
- API já chama roteador somente em `domain=auto`; domínio explícito usa modelo padrão fixo.
- CLI já invalida `result` quando não recebeu `done` ou houve erro.
- Runtime já saiu da CLI do Backend; config do gateway não exige GGUF/chaves privadas dos nós. `--verify-models` na CLI ficou como compatibilidade sem verificação real.
- Frontend já existe, usa texto escapado/token em memória e permite confirmar a origem remota antes de enviar Bearer.

Esses avanços reduzem trabalho, mas **não encerram** terminal/retry/health/metrologia. As pendências abaixo se referem ao código atual.

## 6. Backlog prioritário de integração e robustez

Convenções: **P0** = integridade/segurança/execução; **P1** = validade científica/contratos/reprodução; **P2** = ergonomia/manutenção. “Confirmado” indica inspeção inequívoca ou reprodução pontual; “a validar” exige teste antes de generalizar.

### T01 — P0 — Alinhar os perfis Backend ↔ LLM

**Confirmado por configuração:** todos os perfis do Backend apontam `http://127.0.0.1:810x`; os três perfis LLM declaram `https://...` e passam flags TLS. Nenhum perfil Backend define `backend_ca_file`. O script `generate-local-ca.sh` cria CA/certificado do gateway, **não** os certificados/chaves de cada nó. O fluxo atual dos READMEs não é suficiente para iniciar a topologia nova.

**Implementar:**
1. Dois perfis coerentes: desenvolvimento loopback controlado (HTTP interno explicitamente documentado) e seguro/remoto (HTTPS interno com trust válido). Principal com HTTPS no cliente → gateway.
2. No seguro, URLs Backend HTTPS iguais às URLs públicas dos nós, CA pública/trust bundle correto no gateway e certificados/SAN por host LLM. Nunca copiar chave privada do nó para o Backend.
3. Provisionamento local idempotente, com saída e host/port/SAN configuráveis; não sobrescrever/rotacionar chaves existentes automaticamente. Para hosts remotos, preferir geração da chave/CSR no destino.
4. Documentar correspondência: `redes-1` ↔ `llm-small-a`:8101; `redes-2` ↔ `llm-small-b`:8103; `prontuario-1` ↔ `llm-large-a`:8102. Unificar identidade ou publicar mapping explícito.
5. Separar `bind_host` de URL pública. Loopback só funciona no mesmo host; URL configurável e bind/interface privada para cenário remoto.

**Aceite:** dois domínios completam stream real; réplica adicional atende mesmo modelo; CA errada/SAN errado são recusados; gateway inicia sem pesos/chaves de nó; o README permite reproduzir sem adivinhar arquivos TLS.

### T02 — P0 — Separar retry automático de “cliente pode tentar de novo”

**Confirmado por reprodução pontual:** `Gateway.retry_before_first_delta()` aceita reenfileirar job cujo deadline já venceu. `_event_stream()` usa `retryable` público, cujo conjunto inclui `queue_timeout`, `deadline_exceeded` e `schema_invalid`, para autorizar retry interno.

**Implementar:** allowlist própria de falhas transitórias de nó/transporte, prazo restante verificado antes da reserva e do dispatch, tentativa anterior efetivamente encerrada, no máximo um failover por padrão. Preservar request ID/deadline/idade lógica; registrar cada tentativa imutavelmente. Nunca replay por expiração/erro determinístico. Retry manual é nova resposta/ID e limpa preview. Depois do primeiro delta gerado, erro parcial e fim, sem concatenar outra geração.

**Aceite:** teste expiração em fila com réplica disponível não gera segunda tentativa; deadline não se renova; cancel no intervalo entre tentativas não cria órfão; máximo de tentativas respeitado; sem execução duplicada. Distinguir “parcial gerado” de “parcial recebido”.

### T03 — P0 — Readiness, falha e destino dos pendentes

**Confirmado por código:** scheduler começa saudável; dispatcher não consulta `healthy`; probe periódico consulta todos os nós, mas exceção HTTP é ignorada, podendo manter saudável nó desconectado. HTTP 200 com `status=ok` não verifica modelo/hash/slots. `backend_error` de transporte mid-stream não marca nó indisponível.

**Implementar:**
- Estado inicial desconhecido/não pronto para nós reais; probes de startup e periódicos limitados por timeout/concurrency/backoff/histerese.
- Separar liveness, disponibilidade de atendimento e compatibilidade de modelo/runtime/contexto/template/slots. `status=ok` sozinho não certifica pool.
- Classificar erro de transporte, 5xx, payload/protocolo, input e schema; erro da requisição não derruba nó arbitrariamente.
- Não despachar pendentes em nó indisponível; definir reroute compatível antes de delta ou espera limitada/erro. Preservar ordem, prazo e logs; evitar tempestade de replay.
- Publicar no LLM metadados/versionamento de implantação por mecanismo leve confiável; não implementar segundo balanceador.

**Aceite:** nó desligado desde startup; probe ConnectError depois de sucesso; morte mid-stream com pendentes; restart; serviço errado retornando 200; modelo trocado; slots divergentes. Nenhum job executa em nó incompatível nem fica pendente eternamente.

### T04 — P0 — Terminal transacional e limites dos buffers

**Confirmado por código:** clínica reserva dois espaços para `result`+`done`, mas `event_buffer_size=1` é aceito; nessa configuração o par terminal nunca cabe. Scheduler acumula texto também em Redes. O limite de frame só é testado **após** `httpx.aiter_lines()` construir a linha; uma linha enorme sem newline pode crescer antes da rejeição. `done` pode entrar na fila antes de o estado tornar-se DONE.

**Implementar:**
- Garantir capacidade terminal coerente (buffer mínimo de dois ou mecanismo terminal separado) e transição única atômica. Testar cancelamento/deadline no momento da conclusão.
- Acumular saída integral somente quando necessária à validação clínica; limitar bytes totais, bytes do buffer e tamanho de frame antes de montar linhas ilimitadas.
- Timeout de envio/consumo no caminho ASGI/socket, não só em `Queue.put`; política de desconexão/cancelamento upstream.
- `_fail` não deve esconder perda: contadores de deltas/bytes produzidos, encaminhados e descartados; fila cheia com terminal disponível.
- Erro de escrita de log/close do generator não pode derrubar dispatcher, reclassificar sucesso entregue ou eliminar evento terminal silenciosamente.

**Aceite:** event_buffer=1 não trava clínica; EOF/frame sem newline enorme; cliente TCP que para de ler; corte no último delta/result/done; exceção de logger/validador/aclose. Ativos/tasks/memória voltam ao baseline e há exatamente um terminal coerente ou cancelamento registrado.

### T05 — P0/P1 — Finalização estrita do protocolo interno

O parser já melhorou, mas lê linhas `data:` isoladas e ignora outras linhas; comentários/linhas arbitrárias depois de `[DONE]` podem ser ignorados apesar do contrato atual falar em rejeitar bytes posteriores. Não valida Content-Type nem índice único da choice; alguns tipos/ordens de usage ainda precisam de fixtures.

**Implementar:** contrato real do build fixado, parser incremental de frames completos, choice única/index=0 ou regra explícita, ordem de content/finish/usage/[DONE], validação de contagens/tipos e limites. Distinguir corrupção de protocolo de falha de transporte. Não relaxar a regra para “aceitar qualquer backend”; novos runtimes exigem adapter/convenção própria. Decidir término em `[DONE]` versus verificação de EOF de forma consistente, sem esperar indefinidamente por fechamento desnecessário.

**Aceite:** fixtures obtidas de execução real sanitizada; finish+EOF, [DONE] sem finish, terminais duplicados, múltiplas choices, bytes posteriores, usage malformado, Content-Type errado, UTF-8 inválido e frame incompleto. Sem result/done público de tentativa incompleta.

### T06 — P0 — Cliente web: corrida, protocolo e resultado exportável

**Confirmado por reprodução:** controller aceita `done {}` sem meta/campos obrigatórios como complete; parser aceita terminal sem delimitador final. Por inspeção, mede `ttftObservedMs` no `meta`, não no primeiro delta; continua lendo após done/error. Callbacks de request antigo abortado podem alterar UI de request novo ou repovoar saída após logout. Há retenção intencional de token/input em `lastRequest` para retry, que deve ser invalidada ao limpar sessão.

**Implementar:**
1. Máquina de estados com ID/epoch local de execução; ignorar callbacks obsoletos e invalidar epoch no logout/cancel/nova requisição.
2. Meta única e válida; seq crescente, delta text string, result com schema coerente, done completo/consistente, error terminal. Nunca complete sem meta ou diante de evento inválido.
3. Frames SSE completos como no cliente Python; EOF com frame inacabado não libera download. Atualizar o teste atual que espera emissão de frame sem delimitador.
4. Após primeiro terminal, cancelar/liberar stream e não continuar aplicando dados; validar exatamente uma finalização segundo contrato.
5. TTFT no primeiro `delta.text` não vazio; `meta`, heartbeat e resposta HTTP não contam. Tempo até result e E2E separados.
6. Download apenas do resultado da execução atual, validado + done sem erro; retry limpa preview/metadados/botão antes de iniciar nova resposta.
7. Validação de arquivo/texto coerente com limites do Backend, UTF-8 estrito se declarado. Hoje textarea `required` pode bloquear envio “só arquivo” e o limite de 256 KiB supera o corpo aceito pela API. Corrigir UX sem aumentar limites indiscriminadamente.
8. Não migrar stack por estética. Token só em memória/header; render como texto; bloquear redirects inesperados do fluxo autenticado ou definir política segura explícita; estreitar CSP em implantação para a origem aprovada.

**Aceite:** browser e unitários para meta→heartbeat→delta atrasado, done sem meta/result/schema correto, error+EOF, result+EOF, seq inválida, request A abortado por B, logout durante stream, retry, arquivo sem textarea, HTTP 401/403/422/429/503 e confiança TLS real. Nenhuma saída antiga libera download.

### T07 — P0/P1 — Deadline total, corpo e tipos de configuração

**Confirmado:** existe `request_body_timeout_s` na config, mas API usa literal 15 s. Deadline não interrompe classificação síncrona e só é rechecado depois. URLs de nó são validadas apenas por prefixo. Vários limites float não proíbem infinito; DTO da requisição ainda permite coerção de `max_output_tokens`.

**Implementar:** timeout de corpo = mínimo do limite configurado e tempo restante; instrumentar recepção/leitura/classificação/enqueue; limitar/tratar trabalho CPU pré-fila sem bloquear event loop indefinidamente. Tipos/valores finitos e limites coerentes; URL por parser sem userinfo/query/fragment inválidos; configuração LLM validada contra campos/tipos conhecidos, port/slots/threads/hash/GPU/TLS. Resolver paths conforme regra documentada; hoje paths do Backend e TLS do node dependem do diretório corrente.

**Aceite:** corpo lento, deadline menor que body timeout, NaN/inf, boolean/string em campos inteiros, URL incompleta/porta inválida/credencial embutida, execução fora da raiz com config absoluta e arquivos relativos bem resolvidos.

### T08 — P0/P1 — Hardening de segurança e implantação

**Implementar:** limite de header/token antes de hashing; rates finitos/positivos; provisionar domínios existentes/não vazios, validar arquivo completo e serializar atualizações concorrentes. Rotação/revogação: inicialmente restart documentado e testado basta; reload só se necessário. Pseudônimo por rodada ou HMAC estável com chave local, sem publicar chave.

Uvicorn hoje é iniciado sem política explícita de proxy headers. Definir trust/forwarded_allow_ips ou desabilitar interpretação no acesso direto; testar `X-Forwarded-Proto:https` falso em HTTP. CORS não é autenticação/ACL do runtime. Em rede não confiável, TLS + ACL/auth de serviço com segredo diferente, nunca Bearer do usuário encaminhado ao nó. `/health` público sem informação sensível; `/metrics` restrito no seguro. Definir se catálogo de domínios é público.

**Aceite:** 401/403/429/503 distintos, buckets independentes, auto não burla autorização, header grande, provisionamentos simultâneos, spoof forwarded, CA/SAN incorretos, rotação e captura cifrada autorizada/sanitizada. Não colocar token em URL/argv ou saída de CI.

### T09 — P1 — Balanceamento realmente comparável

RR hoje tem cursor só por domínio; EWMA é global por nó; warm-up sem observações favorece o primeiro nome enquanto nenhuma conclusão existe. Compatibilidade é basicamente igualdade de alias do modelo, não hash/build/template/capacidade verificados.

**Implementar:** pool estável domínio+modelo+perfil compatível; RR por pool; menor fila considera ativos+pendentes, documentando normalização se slots forem heterogêneos; menor latência usa EWMA por classe comparável e exploração/reservas de aquecimento distribuídas. Definir se minimiza serviço observado ou conclusão esperada com fila; não confundir os dois. Reserva permanece atômica no processo único.

**Aceite:** admissões simultâneas antes de primeiras conclusões se distribuem; mistura de domínios/modelos não contamina EWMA; mudança de pool não quebra cursor; réplica com hash/template incompatível é excluída. As três políticas serão comparadas com mesma carga e recursos, não modelos diferentes.

### T10 — P1 — Contratos públicos utilizáveis pelos dois clientes

**Implementar:** Backend autoritativo publica schema de request, payloads/envelopes SSE e HTTP errors, regras de ordem/terminal, limites e catálogo. O `oneOf` atual só modela payloads, é permissivo e sem discriminador do nome do evento; isso pode ser mantido como schema parcial, mas não prova a sequência de protocolo.

Gerar/exportar schema clínico do Pydantic e fixtures reais/simuladas; documentar no OpenAPI o POST e a resposta streaming. Sync/check por versão/hash no Frontend, não imports de filesystem em produção. Backend testa compatibilidade do contrato interno do LLM. Versionar mudanças incompatíveis de schema/evento; adições opcionais podem preservar v1 quando justificadas.

**Aceite:** teste rejeita divergência entre cópias; fixtures válidas passam nos dois clientes; eventos inválidos nunca liberam conclusão/exportação; package/clone funciona sem diretórios irmãos para testes normais.

## 7. Metrologia: implementar antes de medir

### 7.1 Definições fixas

| Métrica | Origem/definição |
| --- | --- |
| TTFT cliente | Início documentado do envio → primeiro delta não vazio recebido; inclui fila/retry/transporte |
| TTFT gateway | Recepção no gateway → primeiro delta real observado; registrar pré-fila e tempo de tentativa separadamente |
| Espera em fila | Enqueue da tentativa → dispatch; espera lógica inclui tentativas/reroute quando houver |
| Serviço | Dispatch → conclusão/cancelamento upstream no gateway; não equivale só a decode |
| E2E cliente | Envio → done válido ou erro final; falhas também entram no registro |
| Resultado utilizável | Envio → result validado + confirmação done; registrar timestamp provisório de result separadamente |
| Taxa runtime | completion_tokens/tempo_decode informado pelo runtime, definição/versionamento explícitos |
| Taxa observada de saída | Contagem válida e janela de geração observada; se usar (n−1)/(t_last−t_first), declarar aproximação por deltas agrupados |
| Vazão agregada | Tokens úteis concluídos/recebidos no intervalo documentado ÷ duração global; não média de taxas individuais |
| Vazão de requisições | Conclusões úteis ÷ duração global; complementar à vazão em tokens/s |

Relógios monotônicos **locais**; não subtrair timestamps absolutos de hosts distintos. `ts_wall` serve para correlação aproximada, não decomposição causal exata de transporte.

### 7.2 T11 — P1 — Completar registros e contagem

O `Job` começa os tempos em enqueue, embora a API já tenha reception timestamp. Adapter não preserva timings completos; log registra tentativas, não um fechamento lógico separado; rejeições pré-fila não geram registros de job; writer faz write+flush síncronos no event loop.

**Implementar:**
- Registro de requisição lógica e snapshots imutáveis por tentativa; request/run/repetition/client/workload IDs, configuração/hash, domínio/modelo/nó/pool/policies, timestamps locais, deadline, retries, erro/status/censura.
- Received/body/read/classify/enqueue/dispatch/first/last/result/terminal; overhead de roteamento separado.
- `delta_count`, bytes gerados/encaminhados/descartados e `completion_tokens` separados. Usage ausente → null e taxa indefinida; tokenizer do mesmo modelo só como estimativa identificada. Nunca deltas/s = tokens/s.
- Preservar usage/timings do runtime e esclarecer se contam reasoning não visível. Desabilitar reasoning por mecanismo suportado no build e medir o efeito; log histórico sugere usar `--reasoning off`, mas verificar suporte antes de mudar.
- Rejeições auth/rate/overload/body/route com ID e motivo sanitizado; throughput não duplica tentativas e erros entram nos denominadores apropriados.
- Writer assíncrono ou thread com fila limitada, drenagem no shutdown e política explícita de perda/falha; não silenciar perda de evidência científica.
- Monitor de CPU/RAM/RSS/PSS/mmap/swap e, se disponível, temperatura/throttling; configuração da máquina e consumo do gerador registrados.

**Aceite:** fórmulas testadas em fixtures com agrupamento de deltas, usage ausente, n<2, retry e falha parcial. Agregados regeneram dos brutos; nenhum texto clínico/prompt/token/chave é logado.

Preferir rodada por ciclos com streams completamente drenados: soma de contagens finais úteis dividida por intervalo global é inequívoca. Para janela fixa, usage final sozinho **não** atribui tokens à janela; definir método de atribuição e tratamento de streams parciais antes do freeze.

## 8. Runtime/modelos e orçamento de recursos

### T12 — P1 — Verificar capacidade e reprodução do runtime

Modelos já disponíveis e íntegros:

| Alias Backend | GGUF local no LLM | Revisão da conversão |
| --- | --- | --- |
| `qwen3-1.7b` | `models/Qwen3-1.7B-Q4_K_M.gguf` | unsloth/Qwen3-1.7B-GGUF `d7f544eead698dbd1f15126ef60b45a1e1933222` |
| `qwen35-4b` | `models/Qwen3.5-4B-Q4_K_M.gguf` | unsloth/Qwen3.5-4B-GGUF `e87f176479d0855a907a41277aca2f8ee7a09523` |

Hashes completos autoritativos em `LLM/models/manifest.json`; não duplicar manualmente fonte de verdade. Registrar ID oficial/model card/licença do modelo-base **e** da conversão, revisão do runtime, versão/argv/template/reasoning, contexto/slots/threads e hash de implantação. Licenças “reported; verify” no manifesto não são confirmação independente.

**Implementar/medir:**
1. 10–20 entradas de desenvolvimento/calibração por candidato atual, modelos testados um por vez antes de topologia completa. Não repetir busca ampla de modelos nem baixar substitutos sem necessidade.
2. Tokenização real de prompt completo+documento+reserva de saída; rejeição explícita de `context_exceeded`, sem truncar silenciosamente fonte. Confirmar significado de `-c` versus `-np` no build.
3. Medir RAM física com PSS quando possível, swap/prefill/decode; tamanho do GGUF e soma de RSS não são RAM exclusiva.
4. Perfil mínimo dois modelos/domínios; perfil de balanceamento duas réplicas pequenas equivalentes. Hosts diferentes preferidos; mesmo host é válido com limitação explícita.
5. Perfis LLM atuais somam 4+2+2 threads se usados juntos: oito threads para alvo de quatro núcleos. Criar orçamento total e documentar processos ociosos/ativos, affinity e consumo; sem prometer ganho físico por duplicar processos.
6. Teste real de cancelamento: fechar HTTP upstream deve encerrar geração/slot no runtime; se há trabalho residual, medir e aguardar disponibilidade antes de despachar de novo.
7. Scripts de download usam raiz/manifesto configuráveis e arquivos temporários/parciais, validação final e falha limpa; testes normais não baixam GBs.
8. Fixar dependências Python transitivas Backend e ferramentas de teste; Nix lock não trava sozinho os ranges pip. Fixar Node; LLM registra build real e testes próprios. GPU só por config futura e sem substituir baseline.

**Aceite:** execução independente de cada produto e instalação limpa; dois modelos cabem em topologia declarada sem swap prejudicial ou bloqueio documentado/fallback validado; cancelamento não deixa fila oculta. Se hardware não comportar, negociar hosts/modelos menores conforme plano inicial, não apresentar réplicas fictícias como LLM real.

## 9. Extração e dados: ferramentas F3 sem apagar a referência

### T13 — P1 — Adapter, integridade e splits

Diretório local atual: `UFES_Redes_Trab2_Backend/data/anonymedbr/processed/reviewed/`. Adapter deve aceitar também caminho externo, ser read-only e não depender dos dados restritos para testes comuns.

1. Ler somente `source_records.jsonl`, `records.jsonl`, `manifest.json`, `provenance.json`; verificar hashes/IDs/unicidade/synthetic e pareamento **por ID**, não posição.
2. Não agregar raw, reviewed-shards, wrong-source ou archived ao conjunto de avaliação. Raw é fonte/proveniência; as anotações clínicas são derivadas.
3. Gerar relatório estrutural separado. Não reanotar/consolidar de novo por conveniência nem sobrescrever os canônicos.
4. Detectar duplicatas/quase duplicatas e famílias antes de split. Meta 100 desenvolvimento/400 avaliação preliminar, seed/IDs/grupos congelados; se grupos impedirem contagem exata, preservar independência e explicar diferença.
5. Selecionar 60 da avaliação para revisão humana estratificada por comprimento, campos ausentes/presentes, negações, hipóteses, medicamentos e vitais. Dois integrantes revisam contra o texto, adjudicam divergências; não se apresentar como profissionais de saúde.
6. Permissões de uso/redistribuição ainda pendentes. Ferramentas/fixtures autorais podem ser implementadas agora; rodadas com dados e publicação dependem de esclarecimento documentado. Nenhuma API externa recebe os textos.

**Aceite:** IDs desordenados continuam pareados corretamente; hash ruim/duplicata/synthetic inválido falham; split reproduz; arquivos originais conservam hash; resultados são novos e locais. Referência atual é LLM, não gold humano.

### T14 — P1 — Semântica clínica, avaliação e exportação

Preservar schema v1 e seus limites documentados; se alterar categorias/semântica incompatível, versionar. Reconciliar alergias desconhecidas/null versus negação explícita/[]; idade explícita; sexo não inferido; hipóteses/histórico/negações; medicamento+atributos; unidades/ranges/PAM. Evidências existentes são paráfrases, não spans/offsets.

**Implementar:**
- Fixtures autorais dos erros históricos: dose de um medicamento não inventa queixa/diagnóstico “Pneumonia”; hipótese de bronquite não vira confirmação. Teste estrutural não é teste de fidelidade do modelo.
- Comparar pequeno/maior primeiro no desenvolvimento; congelar prompt/modelo/schema antes do teste. JSON compacto pode reduzir tokens, mas precisa de avaliação/calibração próprias.
- Métricas: JSON/schema válido, truncamentos, hallucination em ausentes, idade/sexo explícitos, precisão/recall/F1 de entidades e nome+dose+via+frequência, hipóteses/negações/histórico, fidelidade de unidades. Separar presente/ausente e referência LLM/humana.
- Queixa/texto livre por rubrica humana/correspondência limitada; não somente igualdade literal. Normalização fixada antes da avaliação; sem tolerância automática idade ±1 ou PA ±10.
- Cliente de lote assíncrono usa **a mesma API gateway**, TLS/auth/filas; checkpoint/resume por source ID+run/config hash, saída determinística e sem duplicação. Erros preservados/reexecução explícita.
- JSON/JSONL canônicos com metadados montados em Python; CSV por tabela pacientes/diagnósticos/medicamentos/vitais com IDs relacionais, escape de fórmulas de planilha e null/unidades documentados. Só exportar resultado validado+done.

**Aceite:** lote interrompido retoma sem misturar modelo/prompt; parcial/truncado não aparece como válido; tabela não perde dose/via/frequência; nenhum dado restrito é publicado. Não há segunda chamada silenciosa de reparo. FHIR/OCR/CID/SNOMED/diagnóstico automático continuam fora do MVP.

## 10. Inteligência: transformar o piloto em incremento avaliado

### T15 — P1 — Domínio e complexidade com teste independente

`routing.py` treina e avalia no startup; probabilidade é arredondada antes do limiar; grupos precisam conter as duas complexidades, mas não validam claramente um domínio único por grupo. Testes atuais exigem matriz perfeita em templates e não são meta de generalização.

**Implementar:**
1. Dataset autoral novo/versionado, com documentos clínicos reais no **formato sintético da tarefa de extração**, perguntas variadas de Redes, ruído, ambiguidade, fora de domínio e texto adversarial. Não apenas comandos que pedem “compare extrações”.
2. Split por famílias linguísticas/templates e casos; holdout escrito independentemente e não usado para ajustar limiar. Fixar IDs/hash/rubrica humana de domínio e complexidade.
3. Treinamento/avaliação offline, artefato confiável versionado por hash; inferência no startup sem retreinar contra teste. Não carregar pickle remoto/não confiável.
4. Threshold com precisão integral; arredondar só apresentação. Baixa confiança domínio → 422 e pedido explícito; complexidade incerta → política conservadora registrada, sem afirmar qualidade garantida.
5. Complexidade combina tarefa, tokens previstos e exemplos validados por **qualidade/custo** pequeno/maior; comprimento sozinho não é inteligência semântica completa.
6. Auto resolve domínio/modelo e só então aplica autorização; explícito continua fixo. Experimento principal desliga auto para não misturar serviço de modelos diferentes.
7. Reportar acurácia/matriz por classe, fallback/cobertura seletiva, confiança/calibração, overhead p50/p95 e qualidade/custo da política versus sempre pequeno/sempre maior.

**Aceite:** teste independente documentado; exemplos clínicos compatíveis com o contrato; erros/fallback transparentes; decisão de modelo sustentada em dados, não “100% no template”. Não prometer aptidão clínica.

## 11. Filas comparativas: FIFO e prioridade com aging

### T16 — P1 — Política não preemptiva auditável

Preservar fila por nó, proprietário único no gateway e FIFO como baseline. Introduzir configuração de fila separada da de balanceamento.

**Implementar:**
- Sequence ID lógico, enqueue, deadline, classe/estimativa de custo **anterior** à resposta e transições. Estimativa calibrada com task/budget/tokens; não usar tamanho final conhecido após geração.
- Prioridade para respostas previstas curtas, não preemptiva; job longo ativo termina antes de curto novo.
- Aging determinístico configurável: por exemplo promover longo ao cruzar limite escolhido no piloto. Recomputar prioridade ao dispatch; não deixar heap com chave obsoleta.
- Retry/reroute preservam idade/justiça definida e deadline; cancelamento/expiração removem jobs; filas limitadas continuam respeitando ativos+pendentes.
- Registrar classe, estimativa, espera/promoção e impacto nos longos. Não confundir classe semântica com tempo de serviço sem calibrar.

**Aceite:** FIFO estável, desempates, não preempção, fluxo contínuo de curtos sem starvation dos longos, queda/expiração/cancel com prioridades. Simulação e implementação usam a mesma política e estimativa disponível antes do despacho.

## 12. Experimento obrigatório e matrizes de incrementos

### T17 — P1 — Ferramentas a implementar no Backend

Os nomes abaixo são **alvos propostos, ainda não comandos existentes**:

```text
experiments/
  config.py / configs/       # rodada validada e workload referenciado por hash
  calibrate.py              # P, S, output, overhead e recursos, uma solicitação ativa
  predict.py                # previsão serial/simulação a partir da calibração
  closed_load.py            # N clientes assíncronos, uma requisição ativa por cliente
  run_matrix.py             # ordem randomizada, aquecimento, drain e resume
  fault_scenarios.py        # quedas de processos conhecidos, sem pkill amplo
  analyze.py / plot.py      # agregação por repetição e figuras a partir dos brutos
evaluation/                 # adapter/split/rubrica/evaluator e ferramentas de revisão
src/llm_gateway/             # cliente assíncrono compartilhado e políticas reais
tests/                      # carga/simulação/estatística com fixtures sem GGUF
```

Não duplicar parser/validação terminal em CLI, lote e carga; criar núcleo cliente assíncrono reutilizável. Não usar frontend como gerador científico obrigatório.

### 12.1 Hipóteses e calibração anterior

- **H1:** capacidade fixa leva vazão a um teto; N maior aumenta fila/TTFT. Em população fechada a fila não diverge infinitamente.
- **H2:** prioridade não preemptiva reduz esperas/conclusões dos curtos e pode prejudicar longos; aging reduz starvation.
- **H3:** réplicas no mesmo host redistribuem carga, mas não criam CPU/RAM e podem não aumentar vazão.

Calibrar 10–20 prompts fora do teste de qualidade, fixando domínio/modelo/schema, runtime/template/threads/slots, TLS, política, cache e budget. Medir prefill P, serviço S, tokens de saída e distribuição, não só média. Aquecer por requisições completas; não assumir 10 s/60 s suficientes em CPU.

Modelo inicial para um nó/slot, FIFO, think time zero, em ocupação contínua:

```text
X_requests(N) ≈ 1 / E[S]
TTFT(N) ≈ (N - 1) * E[S] + E[P] + transporte
R(N) ≈ N * E[S] + transporte
```

É aproximação serial fechada, não Erlang-C de chegadas abertas. Para múltiplos nós/classes/prioridade, simulação discreta alimentada somente pela calibração anterior. Variabilidade/startup/cache/custo do gateway podem explicar desvio.

Definir antes um limiar operacional de aumento de TTFT; crescimento gradual desde N=2 pode ser o resultado. Salvar **antes da matriz** previsão, hipótese, configuração e hashes/timestamp; commit autorizado ou pacote local datado/hash quando não houver commit. Não ajustar previsão com os dados que ela deveria prever.

### 12.2 Matriz mínima

| ID | Rodada | Controles e evidências |
| --- | --- | --- |
| A — obrigatória | N=1,2,4,8,16; um nó/slot; FIFO; cinco repetições independentes | Domínio explícito/modelo fixo, TLS ligado, contagem válida, TTFT/vazão/erros e previsão |
| B — desafio | Mesma população e mistura fixa curtos/longos; FIFO × prioridade+aging | Políticas de estimativa congeladas; TTFT/E2E/espera por classe e justiça dos longos |
| C — desempenho | ≥2 réplicas reais equivalentes; RR × menor fila × menor latência | Mesma CPU/RAM/config/carga; cinco repetições nos N representativos, ideal todos N |
| D — failover | Queda antes do primeiro delta e durante geração, repetida por cenário | PID específico, momento/attempt/retry, recuperação, parcial perdido, saída válida/erro |
| E — segurança/inteligência | Casos negativos TLS/auth e holdout/qualidade/custo | Rodadas separadas da carga principal; métricas e evidências sem segredos |

A/B/C não misturam modelos variáveis de auto. Tokens de carga têm limites suficientemente altos para não transformar fila em teste de rate limit; limites e contas registrados, nunca segredo. Falhas de segurança usam contas/perfis próprios.

### 12.3 Duração, execução e freeze

1. Piloto escolhe budgets suficientes; 128 tokens não são presumidamente suficientes para prontuário. Limite de saída é teto, não tamanho constante.
2. Meta inicial de aproximadamente dez conclusões por cliente/repetição, ajustada ao custo real antes de medir; registrar redução e baixa precisão de percentis.
3. Repetições em ordem randomizada e registrada; drenar filas entre rodadas, resetar EWMA/buckets/contadores conforme desenho sem apagar logs; pesos residentes e warm-up comparável.
4. Cache de resposta desligado; prefix/KV cache controlado/documentado. Não reiniciar/carregar modelo por request.
5. Registrar recursos, carga externa, swap/throttling/temperatura e gerador; host cliente separado preferível. Se local, medir custo e declarar limitação.
6. Critérios de invalidação anteriores; não descartar uma rodada só porque a própria saturação aumentou latência.
7. Timeouts/503/429/falhas são dados. TTFT de sucessos sozinho é enviesado quando há censura; reportar taxas/thresholds/piores esperas.
8. `run_matrix` recupera execução interrompida sem sobrescrever repetição antiga e só reaproveita quando hashes/config correspondem.

### 12.4 Artefatos e análise

```text
Backend/artifacts/experiments/<run_id>/
  manifest.json                 # versões/hashes/hardware/regras; sem segredos
  config.sanitized.json
  calibration.jsonl
  prediction.json               # anterior aos requests principais
  client_requests.jsonl
  gateway_requests.jsonl
  gateway_attempts.jsonl
  resources.csv
  summary.csv
  figures/
```

Config sanitizada não basta para reproduzir se omitir parâmetros de trabalho; remover segredos, não parâmetros científicos. Dados restritos não entram no pacote publicável. Hash/ID de workload e fixtures autorais permitidas possibilitam reprodução do protocolo sem redistribuir fontes.

Gráficos obrigatórios/prioritários:

1. TTFT cliente × N, previsto/observado, dispersão/IC95% entre repetições, p50/p95 e indicação de erros/censura.
2. Vazão agregada tokens/s × N; requisições/s complementar.
3. Fila/serviço/prefill/decode e tempo até resultado utilizável para explicar gargalo.
4. FIFO × prioridade: métricas curtos/longos e promoções/espera máxima, não apenas média global.
5. Balanceadores: jobs por nó, queue depth, latência/vazão; falhas em tabela/timeline.

IC baseado em repetições, não tokens correlacionados. P95 com poucas amostras exige ressalva. Nunca fabricar gráficos a partir de números do README nem apresentar simulação como medição de LLM.

### 12.5 Resposta à pergunta-desafio

Para conversa, discutir início percebido (TTFT) e fluidez (tokens/s), usando os próprios dados sem alegar preferência humana universal. Para extração JSON, primeiro `{` não é informação útil: comparar também tempo até resultado validado. Mostrar como prioridade muda experiência dos curtos e dos longos sob saturação e como aging limita prejuízo, apoiando-se na matriz B.

## 13. Ordem de execução e critérios de marco

| Etapa | Conteúdo | Dependências | Critério de pronto |
| --- | --- | --- | --- |
| E0 — retomar snapshot | Git/diffs, baseline, contratos e docs de localização | Nenhuma | Trabalho preexistente preservado, baseline e pendências registradas |
| E1 — integração e P0 | T01–T08, testes de defeitos | E0 | HTTPS/HTTP coerentes, retry/deadline/readiness/terminal/cliente seguros |
| E2 — metrologia/contratos | T09–T11, cliente comum, logs completos | E1 | Pool comparável, dados científicos corretos e contrato sincronizado |
| E3 — runtime e qualidade | T12–T15 | E1/E2 | Topologia viável, contexto/cancelamento medidos, ferramentas F3 e router independente |
| E4 — filas e carga | T16–T17, simulação/análise unitária | E2 | FIFO/prioridade/aging, N fechado e fórmulas testados sem pesos |
| E5 — M1/M2 verificáveis | Demo atual, piloto, freeze e previsão | E3/E4 | Núcleo e incrementos demonstráveis; roteiro executável/pré-registro |
| E6 — medição | Matrizes A–E e revisão humana permitida | E5 | Brutos preservados, repetições, erros, gráficos e comparação previsão |
| E7 — M3/reprodução | Docs/CI/fresh setup/relatório/demos | E6 | Relatório ≤6 páginas, resultados regeneráveis e outra pessoa reproduz |

E3/E4 podem avançar independentemente depois dos contratos; não autoriza agentes a editar a mesma interface simultaneamente sem coordenação. Frontend P0 vem antes da demo; polimento visual depois de metrologia/carga. Não “esperar a licença” para implementar ferramentas com fixtures autorais.

### Pacotes sugeridos para distribuir trabalho futuro

- **Backend/robustez:** T02–T05/T07/T09/T11/T16; dono de gateway/scheduler/jobs/metrics/adapters.
- **LLM/integração/qualidade:** T01/T12/T13/T14/T15, coordenando contrato de capacidade e sem alterar API pública sozinho.
- **Frontend/clientes/experimento:** T06/T10/T17, coordenando schema/tempos; segurança T08 revisada transversalmente.

É divisão sugerida de responsabilidade, não instrução para lançar subagentes automaticamente. Dependências de contrato devem ser resolvidas antes de trabalhos paralelos. Cada unidade termina com testes, evidência e atualização do handoff.

## 14. Testes e reprodução que a entrega precisa conter

### Backend

- Regressões dos defeitos confirmados, não apenas casos felizes existentes.
- HTTP real para SSE/overload/cancelamento e cliente lento; MockTransport para protocolo malformado; TLS local/hostname/proxy spoof reais.
- Deadline/retry/readiness com tempo/controladores determinísticos quando possível, evitando sleeps frágeis.
- Cliente compartilhado/lote/carga: terminal, erros HTTP não JSON, transport errors com tempos parciais, invariantes N ativo, resume e contagens.
- Estatística/simulação testadas contra fixtures conhecidas e conservação de jobs/tokens; dados restritos não necessários em CI comum.

### Frontend

- Testes Node existentes + regressões de estados/protocolo/logout/concorrência.
- Build fresco por `npm run build` após conferir que `dist/` não contém trabalho manual; script remove esse diretório gerado.
- Browser E2E com gateway simulado e TLS/CORS/proxy reais: arquivo, preview Unicode, cancel, retry, sem download parcial e ausência de XSS.
- Sem token em localStorage/URL/log/bundle; estado apagado no logout e nenhum callback antigo o repovoa.

### LLM e integração

- unittest de config/manifest/hash/paths/argv e teste de cert/key/protocolo/reasoning compatíveis com build.
- Smoke GGUF opt-in; nenhum download em testes comuns. Readiness/cancelamento/falha precisam de runtime real quando declarados comprovados.
- Refs/hashes dos três produtos + diffs se dirty; só registrar refs limpas como pin completo quando realmente representarem o código executado.
- Cenário com URLs remotas reais ou localhost rotulado explicitamente; nunca alegar distribuição entre computadores de uma execução só local.
- CI independente por produto e job de contrato/smoke simulado; real opt-in com recursos/licenças autorizados.

## 15. Documentação, entregas e cortes seguros

### T18 — P1/P2 — Finalizar documentação honesta

Atualizar READMEs para remover números antigos 81/94 quando apresentarem suíte atual, comando `runtime` já retirado da CLI, `tokens_source=deltas` antigo, pasta `models/` no Backend e descrições contraditórias de remotos/dataset/frontend. Registros históricos devem ficar marcados como históricos, não apagados.

No Backend, criar guia de integração com:

- Arquitetura e fronteiras, portas/URLs/IDs, trust e chaves por host, profiles CPU/remoto/seguro.
- Comandos efetivos de setup/test/start/smoke/falha/calibração/previsão/carga/análise. Marcar comandos propostos como não implementados até existirem.
- Versões/licenças/model cards e restrições dos dados; identidade/commits/push só conforme autorização. Não reescrever histórico nem inventar identidade Git.
- Troubleshooting: OpenSSL só no ambiente declarado, HTTPS↔HTTP incompatíveis, SAN/CA, slot/contexto/timeout e memória/swap.
- Scripts de leitura de token compatíveis com shell documentado; exemplos `read -rsp` são Bash, não assumir zsh compatível.
- Pacote selecionado de resultados sanitizados permitido, com manifestos e script de regeneração; não publicar todo `artifacts/` por acidente.

Relatório até seis páginas: objetivo/topologia; hipóteses/modelo fechado; método e recursos; TTFT/vazão/filas; incrementos e falhas; qualidade/limitações; desafio e conclusão. Priorizar figuras de Redes, não substituir experimento por F1 clínico.

Demos: M1 cinco minutos com dois domínios/modelos e clientes enfileirados; M2 auth 401/403/429/TLS, auto, réplicas e queda; M3 gráficos reais/resultado regenerável e conclusão. Preparar entradas sintéticas curtas que concluam no tempo da demo, sem afirmar que representam toda a avaliação.

**Cortar primeiro se prazo apertar:** framework frontend, grande dashboard, GPU, outros modelos/frameworks, OCR/FHIR/RAG/cache semântico/fine-tuning/integração hospitalar e revisão humana de 500 casos.

**Não cortar silenciosamente:** dois modelos/domínios, filas/stream/métricas corretas, réplicas equivalentes, auth+autorização+rate limit+TLS, auto com escolha pequeno/maior avaliada, erro mid-stream, comparação de fila, N exatos, previsão anterior e repetições/gráficos. Bloqueio de hardware/licença/requisito deve ser informado e negociado, não escondido em “simulação equivalente”.

## 16. Checklist de handoff de cada agente

### Registro de continuidade — 02/11/2026 (E0 + fatia E1)

Esta seção registra somente trabalho observado nesta continuação; não altera o diagnóstico histórico acima nem declara E1 completo.

- **E0:** foram lidos o enunciado, os status e diffs preexistentes dos três repositórios. Nenhum diff local foi descartado, nenhum commit/push foi feito, e artefatos/pesos/dados não foram movidos. Baseline inicial reproduzido: Backend 103 pytest, Frontend 7 Node tests, LLM 5 unittest; manifesto validou ambos os GGUF.
- **T01 parcial:** perfis `cpu_minimal` + `*-dev-http` agora deixam claro HTTP interno só em loopback. Perfis M2 apontam HTTPS e nomes `llm-small-a`, `llm-small-b`, `llm-large-a`, com `backend_ca_file` próprio. Foi acrescentado provisionamento de certificado por nó, idempotente por recusa de overwrite, SAN/configurável e com teste local; geração local de CA do gateway também ganhou SANs adicionais/lock/recusa de overwrite. **Ainda é necessário provisionar nos hosts, montar o trust bundle e validar TLS real ponta a ponta.** O script de certificado self-signed serve ao piloto local, não substitui PKI/CSR aprovado para hosts remotos.
- **T02 parcial:** failover interno tem allowlist própria de falhas de conexão/transporte, confere deadline antes de reservar, não tenta repetir timeout/deadline/erro de schema/protocolo; cliente continua vendo retry manual para códigos públicos. Teste simulado verifica deadline vencido e contrato recusa classes determinísticas. Ainda faltam cenários determinísticos de cancelamento entre tentativas, limite de tentativas, retries auditados como entidade imutável e runtime real.
- **T03 parcial:** nós reais começam indisponíveis, probes iniciais/periódicos concorrentes e limitados alteram indisponibilidade também em ConnectError; dispatcher deixa de iniciar pendentes em nó indisponível. Teste cobre nó desligado no startup. HTTP 200 `status=ok` ainda não comprova hash/modelo/context/template/slots; morte mid-stream e destino/reroute de pendentes precisam de testes/adapters adicionais. `/ready` reporta se algum nó está saudável, sem alegar compatibilidade detalhada.
- **T04 parcial:** buffer mínimo configurável agora reserva `result`+`done`; estado DONE e terminais são publicados sem await entre si. Limite de saída já existente aplica-se a todos os domínios; ainda faltam limite antes de acumular linha do parser HTTP interno e testes de cliente TCP lento/exceções de logger.
- **T06 parcial:** Frontend rejeita EOF em frame incompleto, valida Content-Type, meta única, sequências, result/schema, payload `done`/`error`, ID de request e terminal único; callbacks de epoch antigo são ignorados após nova requisição/logout/cancel, TTFT é primeiro delta não vazio, e download só recebe resultado da execução concluída. Upload passou a UTF-8 estrito e 64 KiB/12.000 caracteres, permitindo arquivo sem texto obrigatório; redirects autenticados são recusados. Testes Node cobrem invariantes principais; ainda falta browser E2E/TLS/CORS real, timeout de consumo e bloquear callbacks antigos do ponto de vista visual em browser.
- **T07/T08 parcial:** body timeout usa config e deadline restante; números temporais/rate precisam ser finitos, URLs dos nós rejeitam credenciais/path/query e HTTP remoto, `max_output_tokens` é strict, auth header tem limite configurável; CLI desabilita proxy headers/forwarded IP implícitos. Testes de proxy em servidor CLI real, provisionamento concorrente de usuário, rotação/revogação e limites de corpo lento seguem pendentes.
- **T10 parcial:** `done` agora carrega `request_id`, também no header `X-Request-ID`; schemas Backend/Frontend estão sincronizados por script verificável. O contrato ainda não é descrição completa da sequência/HTTP/OpenAPI nem compartilhado em fixtures automaticamente com cliente Python.
- **T18 parcial:** README Backend corrigiu números/claims obsoletos de testes/usage e marcou smokes de runtime como históricos; novos guias distinguem loopback-dev e HTTPS. Documentação de integração precisa ser revisada após primeiro runtime real com confiança TLS e configuração efetivamente resolvida.
- **Não executado:** runtime de inferência, build real do llama.cpp, benchmark, carga fechada, análise científica, revisão humana, browser E2E. O baseline foi simulado/HTTP local e testes de parsing/provisionamento.
- **Validação após alterações:** Backend: `ruff check src tests`, `ruff format --check src tests` e 125 testes pytest passaram; `scripts/check-public-contract.sh` passou. Frontend: 12 testes Node, `npm run build`, `cmp` dos contratos e `git diff --check` passaram. LLM: 7 unittest, `scripts/verify-models` (dois hashes) e `git diff --check` passaram. Script CA validado por `bash -n` e execução de provisionamento/verificação com openssl em `/tmp/opencode`; nenhum segredo foi criado nos repositórios.

**Próxima unidade executável:** fechar T01/T03 com prova TLS localhost Backend→nó e configuração idempotente completa (CA agregada sem copiar chaves), adicionar capacidade de implantação/hash em `/health`, depois T04/T05 com parser limitado a bytes antes da linha e fixtures internas sanitizadas. Só então ampliar metrologia (T11), experimento (T17) e declarar marcos.

- [ ] Li enunciado, este plano e código pertinente; não parti do estado pré-código do plano inicial.
- [ ] Conferi Git/diffs nas pastas afetadas e preservei alterações preexistentes.
- [ ] Declarei escopo/IDs Txx e dependências antes de alterar interfaces.
- [ ] Acrescentei regressão de defeito antes ou junto da correção.
- [ ] Registrei comandos/testes executados e limites da evidência (mock, HTTP/TLS, browser, GGUF, benchmark).
- [ ] Mantive Backend único dono de filas/balanceamento/retry/autorização.
- [ ] Não baixei/enviei/publicei/movi dados/pesos/segredos sem autorização.
- [ ] Não fiz instalação global, reset ou limpeza ampla; nenhum push automático.
- [ ] Atualizei contratos/cópias/testes de compatibilidade quando necessário.
- [ ] Atualizei status/documentação sem transformar smoke em conclusão acadêmica.
- [ ] Entreguei arquivos alterados, pendências, riscos e próxima unidade executável.

### Instrução pronta para o próximo agente

> Leia `PLANO_CONTINUIDADE_PROJETO_1_ATUALIZADO.md` na raiz, a seção Projeto 1 do enunciado e os módulos envolvidos. O projeto já tem três repositórios independentes, remotos origin e alterações locais; não remigrar nem resetar. Backend passou 103 testes no devenv; Frontend 7 testes Node; LLM 5 unittest e hashes dos dois GGUF válidos. Isso não é benchmark. Comece por E0/E1: alinhe URLs HTTP do Backend com HTTPS/certificados/CA dos perfis LLM; restrinja retry automático ao prazo/falhas de transporte; corrija readiness/pendentes/terminal/buffers e validação/concorrência/TTFT do frontend. Preserve os avanços já existentes de [DONE], StrictInt, tokens desconhecidos null e domínio explícito fixo. Depois complete métricas/contratos/pools, contexto/recursos/cancelamento real, ferramentas de dados/avaliação e roteador independente; implemente FIFO/prioridade com aging e carga fechada N=1,2,4,8,16. Calibre e salve previsão antes das rodadas com cinco repetições/gráficos. Mantenha três incrementos, inferência local e alvo CPU; dados AnonyMED-BR estão localmente no Backend, com licença pendente, e devem ser preservados read-only. Não iniciar APIs externas, push, instalação global, mudança de stack ou expansão de escopo. Trabalhe em unidades pequenas Txx com testes/evidências e atualize este handoff; peça decisão somente quando houver bloqueio real ou alteração de requisito.
