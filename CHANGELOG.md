# Changelog — Backend

## 22/11/2026 — Entrega

- **Relatório:**
  - seção 5 com a medição do laboratório: tokens/s por pedido, cache de prefixo e fila de 3 clientes com TTFT de 54 s;
  - seção 6 com a resposta da pergunta-desafio a partir dos dados reais.
- **Relatório em PDF:** `docs/RELATORIO.pdf`, gerado do `.md` por `docs/apresentacao/gerar_relatorio_pdf.py`.
- **PDF de apresentação:** tabela da medição do laboratório na parte 4 e índice de páginas atualizado.

## 19/11/2026 — Primeiro teste distribuído no laboratório

- **Funcionou:** gateway no PC-A (grad215) e nó Qwen3 1.7B no PC-B (grad214), na rede 192.168.112.x. O log do
  `llama-server` no B registrou as gerações pedidas pela tela do A (~14–15 tokens/s).
- **Problema:** PCs com zips de pacotes diferentes ficaram com chaves diferentes, e o nó devolveu 401 ao gateway.
- **Novo:** `python3 lab.py chave` (impressão da chave, para comparar entre PCs), `chave --mostrar` e
  `chave --definir` para corrigir na hora; impressão da chave no banner do gateway e na saída do nó.
- **Planejamento:** um único pacote, mandado por e-mail aos três (`docs/LABORATORIO.md`, `docs/PLANO.md`).
- **PDF:** parte 8 com a solução de problemas na rede local (diagnóstico em 4 comandos, mensagens de erro, como provar
  a comunicação, plano B).

## 09/11/2026 — Plano v2

Detalhes, motivos e como conferir: [docs/MUDANCAS.md](docs/MUDANCAS.md). Estado anterior: tag `antes-do-plano-v2`.

**Corrigido**
- `lab.py`: download que vinha truncado sem erro (agora confere o tamanho e retoma com HTTP Range); órfãos ao fechar
  o terminal (SIGHUP tratado, PIDs em `.lab/pids.json`). Os dois foram achados no teste real de 10/11.
- 10 testes que falhavam no Windows (`os.fchmod`, Git Bash, prazo de 0,01 s).
- Vaga presa quando o pedido era cancelado no mesmo instante em que ganhava a vaga. O bug era anterior ao plano e
  apareceu no ensaio do experimento.
- `ClientDisconnect` durante o envio do corpo virava exceção não tratada.

**Novo**
- Política de fila configurável: FIFO ou curtos primeiro com envelhecimento (`queue_policy.py`, `[scheduling]`).
- Evento SSE `queued {position, node}`; `meta` na admissão e repetido em troca de nó (contrato v1.1).
- Migração dos pedidos na fila de um nó que fica fora do ar.
- Vazão agregada e pedidos ativos em `/metrics`.
- Chave de API entre gateway e nós (`api_key_file`), que permite nó em HTTP na LAN.
- O gateway serve a tela (`gateway.frontend_dir`).
- `lab.py`: demo, nó, gateway, experimento, baixar e pacote, num comando.
- `experiments/`: carga em laço fechado, previsão pela lei de Little, gráficos com IC 95%.
- CI no GitHub Actions; `docs/PLANO.md`, `docs/MUDANCAS.md`, `docs/LABORATORIO.md`, `docs/RELATORIO.md`.
- README no formato das instruções de entrega; `requirements.txt`; relatório breve; prazo de 22/11 e a tabela de
  pontos das instruções no `docs/PLANO.md`; experimento com 3 repetições de 20 pedidos por padrão.

**Alterado**
- Roteador semântico opcional e desligado; scikit-learn e NumPy viraram o extra `[router]`.
- "Menor latência" = (pedidos no nó + 1) × EWMA, com reamostragem do nó esquecido.
- Texto cortado no limite de tokens termina com `done` (`finish_reason: "length"`); JSON cortado continua erro.
- Documentação: README curto; planos antigos em `docs/historico/`; enunciado em `docs/ENUNCIADO.md`.

## 02/11/2026

- Gateway, fila por nó, SSE, dois domínios, balanceamento, failover antes do primeiro trecho, segurança M2 e roteador
  piloto (commits do Daniel). Registro completo em `docs/historico/README-02-11.md`.
