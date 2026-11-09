# Esqueleto do relatório (até 6 páginas)

A spec pede um relatório curto na entrega final (M3). Esta é a estrutura proposta, com o tamanho de cada parte e de
onde vem o conteúdo. Os números só entram depois da medição real no laboratório.

| Seção | Tamanho | Conteúdo | Fonte |
|---|---|---|---|
| 1. Introdução | ½ página | O problema (IA como problema de filas, roteamento e transporte), os dois domínios, a soberania digital | `README.md` |
| 2. Arquitetura | 1 página | Um diagrama (repositórios e máquinas) e o caminho de um pedido | `EXPLICACAO.md`, diagramas 1 e 3 |
| 3. Protocolo e decisões | 1 página | SSE × WebSocket, TCP × UDP, event loop, fila com K vagas, failover; tabela curta de decisões | `docs/PLANO.md`, seção 2 |
| 4. Incrementos | 1 página | Desempenho (3 políticas, failover e migração da fila) e Segurança (token, domínio, limite de taxa, TLS, chave dos nós), cada um com a medição dele | cenários 4 e 5 |
| 5. Experimento | 1½ página | Hipótese, previsão (lei de Little) e medição; gráficos TTFT × N e vazão × N com IC 95%; onde a previsão acertou e onde errou, e por quê | `experiments/resultados/<data>/` |
| 6. Pergunta-desafio | ½ página | TTFT ou tokens/s? FIFO × curtos primeiro: box plot por classe; resposta apoiada nos dados | `desafio_ttft_por_classe.png` |
| 7. Limitações e trabalho futuro | ½ página | Um processo de gateway; failover depois do primeiro trecho é erro parcial; CPU sem GPU; roteador e FHIR como trabalho futuro | `README.md`, "Limitações" |

**Para a pergunta-desafio:** uma pessoa lê cerca de 4 a 7 tokens/s (200 a 300 palavras por minuto). Se o tokens/s por
pedido medido ficar acima disso mesmo com a fila cheia, quem conversa sente sobretudo o TTFT. Os dados do cenário 3
dizem se isso acontece com o Qwen3 1.7B na CPU do laboratório.
