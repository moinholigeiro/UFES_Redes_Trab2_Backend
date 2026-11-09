# Changelog — Backend

## 09/11/2026 — Plano v2

Detalhes, motivos e como conferir: [docs/MUDANCAS.md](docs/MUDANCAS.md). Estado anterior: tag `antes-do-plano-v2`.

**Corrigido**
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
- CI no GitHub Actions; `docs/PLANO.md`, `docs/MUDANCAS.md`, `docs/LABORATORIO.md`, `docs/RELATORIO-ESQUELETO.md`.

**Alterado**
- Roteador semântico opcional e desligado; scikit-learn e NumPy viraram o extra `[router]`.
- "Menor latência" = (pedidos no nó + 1) × EWMA, com reamostragem do nó esquecido.
- Texto cortado no limite de tokens termina com `done` (`finish_reason: "length"`); JSON cortado continua erro.
- Documentação: README curto; planos antigos em `docs/historico/`; enunciado em `docs/ENUNCIADO.md`.

## 02/11/2026

- Gateway, fila por nó, SSE, dois domínios, balanceamento, failover antes do primeiro trecho, segurança M2 e roteador
  piloto (commits do Daniel). Registro completo em `docs/historico/README-02-11.md`.
