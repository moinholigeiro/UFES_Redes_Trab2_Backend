# Projetos de Redes de Computadores – Propostas de Trabalho

Oct 21, 2026 · @Magnos

Universidade Federal do Espírito Santo · Centro Tecnológico · Departamento de Informática Redes de Computadores · Prof. Magnos Martinello

Cada projeto combina um serviço de rede real com uma camada de inteligência que dá sentido ao que trafega. Não basta transmitir áudio, vídeo ou arquivos: o sistema precisa entender, verificar ou adaptar o conteúdo, e você precisa medir quanto isso custa em latência, banda e recursos. Os trabalhos podem ser feitos individualmente ou em dupla.

## Como os projetos funcionam

Todos os projetos seguem a mesma estrutura, em quatro camadas:

1. **Núcleo obrigatório.** É o serviço de rede funcionando de ponta a ponta. Sem ele, os incrementos não contam.
2. **Trilhas de incremento.** Há três trilhas: Desempenho, Segurança e Inteligência. A dupla escolhe pelo menos um incremento em duas trilhas diferentes; quem trabalha sozinho escolhe um incremento.
3. **Experimento obrigatório.** Uma hipótese, uma variável controlada (por exemplo, perda de pacotes com `tc netem`), uma métrica e um gráfico. Resultado sem gráfico e sem repetições não é resultado.
4. **Pergunta-desafio.** Uma pergunta conceitual que o relatório deve responder com base nos seus próprios dados.

**Marcos.** M1, ao fim do primeiro terço do prazo, é o núcleo funcionando, com demonstração de 5 minutos. M2, ao fim do segundo terço, são os incrementos e o roteiro do experimento. M3, na entrega final, traz o experimento, o relatório curto (até 6 páginas) e a demonstração.

**Integração entre projetos.** Os projetos podem consumir uns aos outros, e uma integração demonstrada vale bônus de até 10% para as duas equipes envolvidas.

| Projeto que consome | Usa o serviço de | Para quê |
| --- | --- | --- |
| 2 – Áudio | 1 – Gateway de LLMs | Checagem de fatos e resumo das falas transcritas |
| 4 – Vídeo | 1 – Gateway de LLMs | Gerar capítulos e responder perguntas sobre o vídeo |
| 4 – Vídeo | 2 – Áudio (transcrição) | Legendas e busca por trechos falados |
| 3 – P2P | 1 – Gateway de LLMs | Embeddings para busca por conteúdo |
| 1 – Gateway | 3 – P2P | Distribuir os pesos dos modelos (arquivos de GBs) entre os nós de inferência |
| 5 – PolKA | qualquer outro | Transportar o tráfego real de outro projeto por múltiplos caminhos |

## Projeto 1 – Gateway distribuído de LLMs abertos

Um gateway recebe perguntas de vários clientes e as encaminha, em streaming, ao nó de inferência certo para cada domínio, com modelos de pesos abertos rodando localmente (llama.cpp, Ollama, vLLM ou LM Studio). O projeto mostra, na prática, que um serviço de IA é um problema de filas, roteamento e transporte, e que dados e modelos podem ficar sob controle local, em linha com a soberania digital.

**Conceitos de Redes em jogo:** filas e concorrência, streaming sobre HTTP (SSE, chunked) e WebSocket, balanceamento de carga, failover, TLS.

**Núcleo obrigatório.**

- Protocolo entre cliente, gateway e nós (HTTP/REST com SSE, WebSocket ou gRPC), com resposta enviada token a token.
- Pelo menos dois domínios, cada um com modelo, prompt de sistema e parâmetros próprios (por exemplo, assistente da disciplina de Redes e assistente de programação), roteados pelo domínio declarado na requisição.
- Fila por nó com limite de concorrência e atendimento simultâneo de vários clientes.
- Métricas instrumentadas: tempo até o primeiro token (TTFT), tokens por segundo, latência fim a fim e vazão.

**Trilhas de incremento.**

- *Desempenho:* balanceamento entre dois ou mais nós, comparando round-robin, menor fila e menor latência observada; failover quando um nó cai no meio de uma resposta (o que acontece com o streaming em curso?).
- *Desempenho:* cache semântico, que reaproveita respostas para perguntas parecidas, medindo taxa de acerto e economia de tempo.
- *Segurança:* autenticação por token, autorização por domínio, rate limiting por usuário e TLS.
- *Segurança:* "red team" do próprio sistema, com tentativas de prompt injection e de vazamento do prompt de sistema, filtros de defesa e log auditável. Reporte quantos ataques de um conjunto fixo passaram antes e depois dos filtros.
- *Inteligência:* roteamento semântico, em que um classificador escolhe o domínio sozinho e manda perguntas simples para um modelo pequeno e as difíceis para um maior.
- *Inteligência:* RAG com o material da disciplina, avaliando o ganho de qualidade em um conjunto de 20 perguntas com gabarito.

**Experimento obrigatório.** Varie o número de clientes simultâneos (1, 2, 4, 8, 16) e meça TTFT e vazão (tokens/s agregados). Antes de medir, preveja com um modelo simples de fila em que ponto o TTFT dispara, e compare a previsão com a medição.

**Pergunta-desafio.** Para um usuário que conversa com o sistema, o que importa mais: TTFT ou tokens/s? Como a política de fila do gateway (FIFO, prioridade para respostas curtas) muda essa experiência quando o sistema está saturado?

## Projeto 2 – Áudio ao vivo com transcrição e checagem de fatos

Um servidor transmite áudio ao vivo (uma aula, um debate, um podcast) para vários ouvintes. Em paralelo, transcreve as falas e marca em tempo real as afirmações verificáveis como "confirmada", "contestada" ou "sem evidência". O desafio de Redes é sincronizar dois fluxos de natureza diferente: o áudio, que tolera perdas mas não atrasos, e o texto, que tolera atrasos mas não perdas.

**Conceitos de Redes em jogo:** UDP e RTP, jitter e buffer de reprodução, perda de pacotes, codecs (PCM e Opus), multicast, sincronização por marcas de tempo, TCP/WebSocket para o canal de texto.

**Núcleo obrigatório.**

- Transmissão de áudio em pacotes sobre UDP, com número de sequência e marca de tempo (estilo RTP), para vários clientes simultâneos.
- Buffer de jitter no cliente, com tamanho configurável, e contagem de pacotes perdidos e atrasados.
- Controles de reprodução: pausar, continuar e parar.
- Transcrição em tempo real com um modelo local (whisper.cpp ou faster-whisper), enviada aos clientes por um canal separado (WebSocket) e exibida como legenda sincronizada ao áudio pelas marcas de tempo.

**Trilhas de incremento.**

- *Inteligência:* checagem de fatos. Extraia as afirmações verificáveis da transcrição e consulte um LLM local com RAG sobre uma base de referência escolhida pela equipe (por exemplo, o livro-texto de Redes para checar uma aula, ou dados públicos do IBGE para checar um discurso). Cada afirmação recebe um selo e a fonte consultada. Monte um conjunto de teste com 30 afirmações, metade verdadeiras e metade falsas, e reporte precisão e revocação.
- *Inteligência:* resumo ao vivo, em que um ouvinte que entra no meio da transmissão recebe um resumo do que já foi dito.
- *Desempenho:* ocultação de perdas (repetir ou interpolar o último quadro) e FEC simples (um pacote de paridade a cada N), medindo o custo em banda.
- *Desempenho:* sincronização entre ouvintes, para que todos escutem o mesmo trecho com diferença menor que 100 ms.
- *Segurança:* acesso apenas para usuários autenticados e áudio cifrado (DTLS, SRTP ou AES-GCM por pacote).
- *Segurança:* integridade da transcrição. Assine digitalmente cada trecho transcrito, para que um cliente detecte uma legenda adulterada no caminho.

**Experimento obrigatório.** Com `tc netem`, aplique perda de 0%, 1%, 5%, 10% e 20% no enlace do áudio. Meça a taxa de erro de palavras (WER) da transcrição feita no cliente, comparando com a transcrição do áudio original, para PCM e para Opus. Inclua no relatório o orçamento de latência: do microfone até a legenda aparecer na tela, onde cada milissegundo é gasto.

**Pergunta-desafio.** Onde a transcrição deve rodar: no servidor, sobre o áudio limpo, ou em cada cliente, sobre o áudio que chegou com perdas? Discuta qualidade, latência, banda, privacidade e escala com base nos seus dados.

## Projeto 3 – Rede P2P com integridade e busca por conteúdo

Cada nó é ao mesmo tempo cliente e servidor e troca arquivos em blocos diretamente com os outros, como no BitTorrent. A rede precisa continuar funcionando quando nós entram e saem, quando alguém só baixa sem compartilhar e quando um par malicioso envia blocos corrompidos. Como caso de uso real, a rede pode distribuir os pesos dos modelos do Projeto 1, arquivos de vários GB, entre as máquinas do laboratório.

**Conceitos de Redes em jogo:** arquitetura P2P versus cliente-servidor, descoberta de pares, tabelas hash distribuídas (DHT), divisão em blocos, NAT, incentivos e free-riding.

**Núcleo obrigatório.**

- Descoberta de pares, seja por um tracker simples ou por broadcast/multicast na rede local.
- Arquivos divididos em blocos de tamanho fixo, com download paralelo de blocos vindos de pares diferentes.
- Verificação de integridade de cada bloco por hash (SHA-256), com o arquivo descrito por um manifesto.
- Atualização dinâmica da lista de pares ativos, com detecção de saída por heartbeat.

**Trilhas de incremento.**

- *Desempenho:* política "mais raro primeiro" (rarest-first) versus sequencial, medindo o efeito na disponibilidade do arquivo quando a semente original sai.
- *Desempenho:* incentivo ao compartilhamento (tit-for-tat), demonstrando que um free-rider passa a baixar mais devagar.
- *Desempenho:* substituir o tracker por uma DHT (Kademlia simplificada) e medir quantos saltos uma busca leva conforme a rede cresce.
- *Segurança:* árvore de Merkle no manifesto e manifesto assinado pelo publicador, de modo que um par malicioso seja detectado e banido automaticamente.
- *Inteligência:* busca por conteúdo, não por nome. Cada nó calcula embeddings dos seus documentos (por exemplo, "slides que explicam controle de congestionamento") e a busca semântica é distribuída entre os pares.

**Experimento obrigatório.** Compare o tempo para distribuir um arquivo de 1 GB para N = 2, 4, 8 e 16 nós (use containers ou Mininet) no modo P2P e no modo cliente-servidor, com o mesmo limite de banda de upload por nó. Plote também a curva teórica do tempo mínimo de distribuição vista em aula e compare-a com a medição.

**Pergunta-desafio.** O P2P escala "de graça"? Identifique nos seus dados o ponto em que o gargalo deixa de ser o upload da semente e passa a ser outro fator, e diga qual é esse fator.

## Projeto 4 – Vídeo sob demanda adaptativo e navegável por fala

Um servidor entrega vídeo em segmentos, no estilo DASH, e o cliente escolhe a qualidade de cada segmento conforme a rede. Além de assistir, o usuário pode navegar pelo conteúdo: pedir "ir para o trecho em que o professor explica o three-way handshake" e o player salta para lá. O desafio central é medir a qualidade de experiência (QoE), e não apenas a taxa de bits.

**Conceitos de Redes em jogo:** HTTP como transporte de mídia, segmentação e manifestos, estimação de banda, algoritmos de adaptação de taxa (ABR), buffers, CDN e cache.

**Núcleo obrigatório.**

- Vídeo codificado em pelo menos três qualidades (por exemplo, 360p, 720p e 1080p com ffmpeg) e dividido em segmentos de 2 a 4 s, com manifesto.
- Servidor HTTP que entrega manifesto e segmentos, e cliente que baixa, mantém um buffer e reproduz.
- Controles de play, pause e seek, sendo que o seek busca o segmento certo sem baixar o vídeo inteiro.
- Registro, no cliente, de bitrate por segmento, nível do buffer, travamentos (rebuffering) e trocas de qualidade.

**Trilhas de incremento.**

- *Desempenho:* dois algoritmos de ABR, um baseado em vazão (média da banda dos últimos segmentos) e outro baseado em buffer (no estilo BBA ou BOLA), comparados no mesmo traço de banda.
- *Desempenho:* CDN simples, com dois servidores de borda que fazem cache de segmentos e um redirecionador que escolhe o mais próximo ou o menos carregado.
- *Segurança:* URLs assinadas com validade (token e expiração) e segmentos cifrados com AES-128, com chave entregue apenas a usuários autorizados.
- *Inteligência:* capítulos e busca por fala. Transcreva o áudio (pode usar o serviço do Projeto 2), gere capítulos com um LLM local e indexe a transcrição para que uma pergunta em linguagem natural leve ao instante certo do vídeo.
- *Inteligência:* perguntas sobre o vídeo, em que o usuário pausa e pergunta "o que ele quis dizer com janela deslizante?" e recebe uma resposta baseada no trecho assistido.

**Experimento obrigatório.** Crie com `tc` um traço de banda variável que se repita igual em cada execução (por exemplo, 5 Mbit/s, queda para 1 Mbit/s por 20 s, volta a 5 Mbit/s). Para cada algoritmo de ABR, reporte bitrate médio, tempo total travado, número de trocas de qualidade e uma métrica de QoE que combine os três. Plote, no mesmo gráfico, a banda disponível, o bitrate escolhido e o nível do buffer ao longo do tempo.

**Pergunta-desafio.** Por que um algoritmo que estima a banda com precisão ainda pode travar o vídeo? Explique com um trecho do seu gráfico em que a escolha de bitrate foi "correta" e mesmo assim o buffer esvaziou, ou mostre por que isso não ocorreu.

## Projeto 5 – PolKA eBPF com roteamento adaptativo e prova de trânsito (Yuri + Felipe)

A partir do repositório [nerds-ufes/polka-eBPF](https://github.com/nerds-ufes/polka-eBPF), estenda o roteamento por resíduos do PolKA. Cada pacote carrega um route-ID que não muda ao longo do caminho, e cada nó obtém sua porta de saída pelo resto da divisão polinomial (em GF(2)) desse identificador pelo seu próprio identificador de nó. A extensão deve tornar a escolha de caminhos adaptativa, observável e verificável, tudo no plano de dados Linux via eBPF.

**Conceitos de Redes em jogo:** roteamento na origem, plano de dados versus plano de controle, multicaminho, reordenação de pacotes, medição ativa e passiva, integridade de caminho.

**Núcleo obrigatório.**

- Explicar e demonstrar, com um exemplo calculado à mão, como um route-ID codifica um caminho e como cada nó extrai a porta de saída.
- Topologia com pelo menos dois caminhos disjuntos entre origem e destino (Mininet, containers ou namespaces).
- Seleção de caminho pela aplicação no host de origem, com troca de caminho sem reiniciar o fluxo.
- Coleta, no eBPF, de métricas por route-ID (latência, perda e vazão), lidas por um agente em espaço de usuário.

**Trilhas de incremento.**

- *Desempenho:* envio simultâneo por múltiplos caminhos com reordenação no destino, no estilo MPTCP, medindo o ganho de vazão e o custo da reordenação.
- *Desempenho:* política adaptativa que desloca o tráfego quando um caminho congestiona, e failover que reage à queda de enlace. Meça o tempo de recuperação.
- *Desempenho:* exportar métricas via Prometheus ou gRPC, com painel em tempo real, que pode ser um app Android com comandos para ativar e desativar rotas.
- *Segurança:* prova de trânsito, em que cada nó acrescenta ao pacote uma marca HMAC encadeada, de modo que o destino verifique se o pacote passou de fato pelo caminho prometido. Mostre um ataque de desvio de rota sendo detectado.
- *Segurança:* registrar as provas de trânsito em uma blockchain permissionada (Besu), para auditoria posterior.
- *Inteligência:* um preditor simples (regressão linear ou média móvel exponencial) que antecipa a degradação de um caminho a partir das métricas recentes e troca de rota antes da perda acontecer.

**Experimento obrigatório.** Com um fluxo contínuo, degrade um dos caminhos com `tc netem` (aumento de atraso e depois queda do enlace). Compare três políticas: caminho fixo, troca reativa (após detectar perda) e troca preditiva. Reporte, para cada uma, vazão ao longo do tempo, pacotes perdidos e tempo até a recuperação.

**Pergunta-desafio.** Por que tirar o estado de roteamento dos nós do núcleo e colocá-lo no pacote facilita a troca rápida de caminho? Qual é o preço dessa escolha em cabeçalho, segurança e verificação, segundo as suas medições?

## Avaliação e ferramentas

| Critério | Peso |
| --- | --- |
| Núcleo obrigatório funcionando na demonstração | 30% |
| Incrementos, pela profundidade e não pela quantidade | 25% |
| Experimento: hipótese, repetições, gráficos e análise | 25% |
| Resposta à pergunta-desafio sustentada pelos próprios dados | 10% |
| Código organizado, README reproduzível e apresentação | 10% |
| Bônus: integração demonstrada com outro projeto | até +10% |

**Ferramentas úteis.**

- Modelos locais: [LM Studio](https://lmstudio.ai/), com bom suporte a Linux, interface por [linha de comando](https://lmstudio.ai/docs/cli) e [API para Python](https://lmstudio.ai/docs/python). Para servidor, o [llmster](https://lmstudio.ai/download) oferece comunicação segura. Alternativas: Ollama, llama.cpp e vLLM.
- Transcrição local: whisper.cpp ou faster-whisper.
- Mídia: ffmpeg para codificar, segmentar e gerar fluxos de teste.
- Emulação de rede: `tc netem` (atraso, perda, jitter, limite de banda), Mininet, containers Docker/Podman e network namespaces.
- Medição: `iperf3`, `ab`, `wrk`, Wireshark/tcpdump e Prometheus com Grafana.
