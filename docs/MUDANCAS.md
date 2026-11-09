# O que mudou em 09/11/2026 — guia para a equipe

Este documento é para o Daniel e a Lívia (e para quem for à entrevista técnica) entenderem as mudanças feitas a partir da
revisão de 09/11, sem precisar ler cada diff. O raciocínio de cada decisão está em [PLANO.md](PLANO.md), seção 2.

**Como conferir ou desfazer:** o estado anterior está na tag `antes-do-plano-v2`, nos três repositórios.

```bash
git log --oneline antes-do-plano-v2..HEAD          # os commits deste plano
git diff antes-do-plano-v2 -- src/llm_gateway/scheduler.py
git revert <commit>                                # desfaz um assunto sem perder os outros
```

**Discordou de alguma coisa?** Escreva na seção "Comentários da equipe", no fim deste arquivo, e a gente decide junto.

---

## Resumo em uma tabela

| # | Mudança | Repo | Decisão | Teste que prova |
|---|---|---|---|---|
| 1 | 10 testes que falhavam no Windows foram corrigidos | Backend | — | `test_security.py`, `test_failover.py` |
| 2 | 4 testes do LLM que falhavam no Windows foram corrigidos | LLM | — | `tests/test_node.py` |
| 3 | Roteador semântico ficou **opcional e desligado** | Backend, Frontend | D3 | `test_routing.py` (pula sem scikit-learn) |
| 4 | **Chave de API** entre gateway e nós (HTTP na LAN) | Backend, LLM | D4 | `test_api_key_is_sent_as_bearer_and_401_is_reported`, `test_api_key_file_is_passed_to_runtime_and_allows_lan_http` |
| 5 | **Política de fila**: FIFO ou curtos primeiro com envelhecimento | Backend | D12 | `test_short_first_*`, `test_fifo_keeps_arrival_order` |
| 6 | Evento **`queued`** com a posição; `meta` na admissão | Backend, Frontend | D13 | `test_queued_events_report_position_and_its_decrease`; 3 testes do controller |
| 7 | Pedidos na fila de um nó que caiu **migram** para outra réplica | Backend | D10 | `test_pending_requests_migrate_when_node_goes_down` |
| 8 | "Menor latência" considera a fila e reexamina o nó esquecido | Backend | D11 | `test_least_latency_accounts_for_queue_length`, `test_least_latency_periodically_retries_forgotten_node` |
| 9 | **Vazão agregada** em `/metrics` | Backend | — | `test_throughput_counts_requests_and_tokens_in_window` |
| 10 | Texto cortado no limite de tokens termina com `done` (`length`) | Backend, Frontend | D6 | `test_text_answer_cut_at_token_limit_ends_with_done_length` |
| 11 | O gateway serve a tela na mesma origem | Backend, Frontend | D16 | `test_gateway_serves_frontend_when_configured` |
| 12 | **Bug da vaga presa** corrigido (achado no ensaio) | Backend | — | `test_cancel_before_task_starts_releases_the_slot` |
| 13 | `ClientDisconnect` durante o envio vira 400 | Backend | — | — |
| 14 | **`lab.py`**: um comando para o laboratório | Backend, LLM | D2, D5 | Ensaio completo no Ubuntu 24.04 (ver o fim deste arquivo) |
| 15 | **Ferramentas do experimento**: carga, previsão e gráficos | Backend | D6–D8 | Ensaio simulado no Ubuntu |
| 16 | Tela: posição na fila, métricas e cartões do prontuário | Frontend | D16 | `tests/controller.test.js` |
| 17 | CI no GitHub Actions nos três repositórios | todos | — | Aba Actions |
| 18 | Documentação reorganizada | todos | D17 | — |

---

## As mudanças, uma a uma

### 1. Testes do Windows (Backend)

- **Antes:** 10 testes falhavam no Windows. Nove deles passavam por `security.py:210`, que chamava `os.fchmod`, função
  que só existe em Linux e macOS. Quando ela falhava, o arquivo temporário ficava aberto e a limpeza também falhava. O
  décimo era instável: usava um prazo de 0,01 s.
- **Agora:** o arquivo é fechado pelo `with` mesmo com erro, e o `fchmod` só roda onde existe. O teste instável usa
  0,3 s de prazo contra 1,0 s de atraso do nó. O script da CA exporta `MSYS_NO_PATHCONV=1`, porque o Git Bash
  convertia `/CN=...` em caminho do Windows.
- **Efeito no Linux:** nenhum. As permissões continuam `0600`.

### 2. Testes do Windows (LLM)

Os testes escreviam caminhos do Windows dentro do TOML (`C:\Users\...`). Para o TOML, `\U` é um escape inválido. Agora
os caminhos vão com `as_posix()`. O script de certificado ganhou o mesmo `MSYS_NO_PATHCONV`.

### 3. Roteador semântico opcional (D3)

- **Antes:** ligado nos perfis M2, e o scikit-learn e o NumPy eram obrigatórios na instalação.
- **Agora:** o código continua em `routing.py`, mas desligado nos perfis, e as dependências viraram o extra
  `pip install -e .[router]`. O `api.py` e o `cli.py` importam o roteador só quando ele está ligado. A opção
  "Automático" saiu da tela.
- **Por quê:** a spec pede incremento em duas trilhas, e Desempenho + Segurança cumprem isso. O piloto tinha 100% de
  acerto em 32 frases geradas por template, o que não se defende numa entrevista. Se o professor pedir a terceira trilha
  para o trio, basta ligar `[router] enabled = true`.

### 4. Chave de API entre gateway e nós (D4)

- **Antes:** nó fora do `127.0.0.1` só em HTTPS, com certificado por máquina e uma CA para distribuir.
- **Agora:** `api_key_file` no nó (repo LLM vira `--api-key-file` do `llama-server`) e no gateway (manda
  `Authorization: Bearer <chave>`). Com a chave, o nó pode ficar em HTTP na rede do laboratório; sem ela, a regra antiga
  vale. O HTTPS por nó continua funcionando, só saiu do caminho padrão.
- **O que protege o quê:** o TLS entre cliente e gateway protege o token e o conteúdo no caminho do usuário. A chave
  impede que outro aluno do laboratório use o nosso nó. O tráfego gateway ↔ nó na LAN fica visível no Wireshark, o que
  é útil para a apresentação e aceitável para dados sintéticos.

### 5. Política de fila (D12)

- **Novo arquivo:** `src/llm_gateway/queue_policy.py`, com duas funções puras.
  - `fifo`: ordem de chegada.
  - `short_first`: menor `max_output_tokens` primeiro. Quem espera mais que `aging_s` (padrão 30 s) vai para a frente,
    para que um pedido longo não espere para sempre.
- **Configuração:** `[scheduling] policy = "fifo" | "short_first"`, mais `aging_s`.
- **Por quê:** sem a segunda política, não há como responder à pergunta-desafio com dados.

### 6. Evento `queued` e `meta` na admissão (D13) — contrato v1.1

- **Antes:** o `meta` só saía junto do primeiro trecho, e na fila o cliente via só `: keepalive`.
- **Agora:**
  - o `meta` sai na admissão;
  - `queued {position, node}` sai na admissão e a cada mudança de posição (1 = o próximo);
  - se o pedido muda de nó antes do primeiro trecho (failover ou migração), sai um novo `meta`, com `attempt` maior.
- **Contrato:** [`contracts/public/v1/README.md`](../contracts/public/v1/README.md). O Frontend tem a cópia, conferida
  por `scripts/check-public-contract.sh`.
- **Testes antigos:** onde conferiam a sequência exata de eventos, passaram a ignorar o `queued`.

### 7. Migração da fila de um nó que caiu (D10)

- **Antes:** só o pedido que falhou ia para outra réplica. Os que esperavam na fila do nó morto ficavam parados até o
  nó voltar ou até estourar `queue_timeout_s`.
- **Agora:** toda mudança de saúde passa por `NodeScheduler.set_health()`. Quando o nó fica fora do ar, ela chama
  `Gateway.migrate_pending()`, que leva cada pedido da fila para uma réplica saudável do mesmo modelo. Se nenhuma
  aceitar, o pedido continua onde estava.
- **O que não mudou:** pedido que já recebeu trechos continua terminando com `error` e `partial=true` (decisão D9).

### 8. "Menor latência" corrigida (D11)

- **Antes:** ordenava pelo EWMA do tempo de serviço. Isso tinha três problemas:
  - o tempo depende do tamanho da resposta, não da velocidade do nó;
  - a política ignorava a fila, e mandava tudo para o nó "rápido" até ele lotar;
  - um nó lento uma vez nunca mais era medido.
- **Agora:** espera prevista = (pedidos no nó + 1) × EWMA. A cada 20 decisões, o nó há mais tempo sem ser o primeiro
  passa à frente uma vez (reamostragem).

### 9. Vazão agregada

`/metrics` mostra, por nó e no total, pedidos/s e tokens/s concluídos nos últimos 60 s. Também mostra `active_jobs`, a
lista dos pedidos ocupando vaga, sem texto. Foi por essa lista que o bug 12 apareceu.

### 10. Texto cortado no limite de tokens

- **Antes:** qualquer resposta cortada em `max_output_tokens` virava erro `truncated`.
- **Agora:** em texto, o `done` sai com `finish_reason: "length"` e a tela mostra "cortada no limite de tokens". Em
  JSON (prontuário), um documento cortado é inválido, então continua erro.
- **Por quê:** o experimento usa `max_tokens` fixo para cada pedido ter o mesmo tamanho. Antes, todos virariam erro.

### 11. Tela servida pelo gateway

`[gateway] frontend_dir = "../UFES_Redes_Trab2_Frontend"`: o gateway serve `/` e `/src/*`. Assim a tela fica na mesma
origem da API, sem CORS e sem outro servidor. A tela usa a própria origem como URL do Backend.

### 12. Bug da vaga presa (achado pelo ensaio)

- **Sintoma:** depois de uma rodada de carga, a fila parou. `active_jobs` mostrava um pedido "ativo" havia 265 s, com 0
  trechos.
- **Causa:** o cliente desconectou no mesmo instante em que o pedido ganhou a vaga. O `task.cancel()` chegou antes de a
  tarefa dar o primeiro passo, e nesse caso o asyncio descarta a corrotina **sem executar o `try/finally`** de `_run`.
  A vaga nunca era liberada.
- **Correção:** um callback de término da tarefa (`_release_if_never_ran`) libera a vaga nesse caso. O teste de
  regressão falha sem a correção e passa com ela.
- **Importante:** o bug já existia antes do plano. Só a carga em laço fechado o expôs. Sem o ensaio, ele apareceria no
  meio do experimento real.

### 13. `ClientDisconnect` durante o envio

Se o cliente desiste enquanto envia o corpo, o gateway responde 400 `client_disconnected` em vez de registrar uma
exceção não tratada. Nada tinha sido admitido, então não há o que liberar.

### 14. `lab.py` (D2, D5)

Um comando por papel de máquina: `demo`, `no`, `gateway`, `experimento`, `baixar`, `pacote`. Ele faz sozinho:

- cria o `.venv`, usando o `uv` quando o Python é antigo ou não tem `venv`, como no Ubuntu do teste;
- baixa o `llama-server` oficial (b12211) e os modelos, conferindo o SHA-256;
- gera a chave dos nós, o token e o certificado do gateway.

O passo a passo está em [LABORATORIO.md](LABORATORIO.md). No repo LLM, o `node.py` ganhou `--bin` (e a variável
`LLAMA_SERVER`) para usar esse binário sem o devenv. No Windows, ele roda o `llama-server` como filho, porque o
`execvp` perderia o controle do processo.

### 15. Ferramentas do experimento

Em `experiments/`:

| Arquivo | O que faz |
|---|---|
| `carga.py` | N clientes em laço fechado, um CSV por execução |
| `previsao.py` | Lei de Little, gravada antes de medir |
| `graficos.py` | TTFT e vazão × N, com IC 95% e a curva prevista; box plot do desafio; `resumo.md` |
| `perguntas.txt` | 20 perguntas longas, para que todos os pedidos tenham o mesmo tamanho |

O `carga.py` descarta a primeira leva de N pedidos (o transitório). Sem isso, o ensaio mostrou um viés: com N = 16, o
TTFT medido ficou em 6 s contra 16 s previstos, porque só os pedidos que esperaram pouco chegavam a concluir. Três
testes cobrem as ferramentas (`tests/test_experimentos.py`). Explicação completa em
[experiments/README.md](../experiments/README.md).

### 16. Tela (Frontend)

- **Novidades:** posição na fila ao vivo; painel de métricas (TTFT e latência medidos no navegador, tokens e tokens/s
  informados pelo runtime); prontuário em cartões (`cards.js`, só `textContent`).
- **Saíram:** a opção "Automático" e o código morto `isPrivateIpv4`.

### 17. CI

`.github/workflows/ci.yml` nos três repositórios:
- **Backend:** lint e `pytest`;
- **Frontend:** `npm test` e `npm run build`;
- **LLM:** `unittest`.

### 18. Documentação

- **Movidos:** os planos antigos e o README de 02/11 estão em `docs/historico/`, sem alteração. O enunciado está em
  `docs/ENUNCIADO.md`.
- **Reescritos:** os READMEs, mais curtos.
- **Diagramas:** os `EXPLICACAO.md` dos três repos ganharam os diagramas.

---

## Depois: instruções de entrega e prazo (09/11, à tarde)

- **Prazo: 22/11/2026.** As datas de 26/10 e 08/11 dos documentos anteriores estavam erradas.
- **Nota.** As instruções de entrega ([INSTRUCOES-ENTREGA.pdf](INSTRUCOES-ENTREGA.pdf)) dão **40 dos 100 pontos a
  "conhecimento sobre o código"**. Por isso a simplificação e os diagramas viraram a prioridade (ver `PLANO.md`).
- **README** no formato pedido (descrição, tecnologias, como executar, como testar, funcionalidades, melhorias), mais um
  `requirements.txt`.
- **Relatório breve** escrito em [RELATORIO.md](RELATORIO.md). Falta preencher a medição real.
- **Experimento:** o padrão do `lab.py experimento` passou para 3 repetições de 20 pedidos, ~3 a 4 h na CPU.

## O que NÃO mudou

- Os prompts, o schema `prontuario-v1`, os modelos, o parser estrito do runtime e os limites de bytes e de prazo.
- A semântica de failover depois do primeiro trecho: erro parcial, sem concatenar respostas.
- Os perfis `cpu_minimal`, `m2_secure` e `m2_replicas`, fora o roteador desligado.
- O devenv (Nix) continua funcionando como antes.

## Como isto foi verificado

| Verificação | Resultado |
|---|---|
| Suíte do Backend (Windows, Python 3.12) | 145 testes, todos passando; `ruff` sem avisos |
| Suíte do Frontend | 15 testes, todos passando |
| Suíte do LLM | 10 testes, todos passando |
| `lab.py experimento --simulado` no Ubuntu 24.04 (WSL), sem `python3-venv` | Caminho completo: uv → venv → gateway → calibração → previsão → carga → desafio → gráficos |
| `lab.py demo --leve` com o modelo real no Ubuntu 24.04 | Ver o CHANGELOG da data |

## Comentários da equipe

_(escreva aqui: nome, data, o que discorda e por quê)_
