# Gateway distribuído de LLMs abertos

Trabalho 2 de Redes de Computadores (INF16158) · UFES · Prof. Magnos Martinello · equipe: Daniel, Lívia e Eduardo.
Entrega em **22/11/2026**.

## Descrição

Projeto 1 da spec: um **gateway** recebe pedidos de vários clientes, coloca cada pedido na **fila do nó de inferência**
certo para o domínio e devolve a resposta **token a token**, por **SSE** sobre HTTPS. Os modelos são de pesos abertos e
rodam localmente no `llama-server` (llama.cpp): Qwen3 1.7B e Qwen3.5 4B. Os dados e os modelos não saem das máquinas
da equipe.

Dois domínios, cada um com modelo, prompt e parâmetros próprios:

- **`redes`**: assistente da disciplina de Redes;
- **`prontuario`**: extrai de um prontuário **sintético** um JSON validado (idade, sexo, queixa, diagnósticos,
  medicamentos, alergias, sinais vitais).

Os desafios de redes e de programação concorrente que o trabalho ataca:

- **Fila por nó com K vagas:** quem espera recebe a posição na fila.
- **Concorrência:** um event loop (asyncio) atende todos os clientes; o trabalho pesado roda nos processos dos nós.
- **Distribuição:** os nós ficam em outras máquinas da rede e são escolhidos por três políticas de balanceamento.
- **Failover:** a fila de um nó que cai migra para outra réplica.
- **Segurança:** token, autorização por domínio, limite de taxa, TLS e chave entre gateway e nós.
- **Medição:** TTFT, tokens/s e vazão sob carga crescente, comparados com uma previsão feita antes pela lei de Little.

> Sistema acadêmico, só com dados sintéticos. Não use para diagnóstico ou qualquer decisão de saúde.

O sistema está em três repositórios, que ficam **lado a lado na mesma pasta**:

| Repositório | Papel |
|---|---|
| **UFES_Redes_Trab2_Backend** (este) | O **servidor**: gateway, fila, balanceamento, failover, segurança e métricas; o cliente de terminal; os experimentos; o `lab.py` |
| UFES_Redes_Trab2_LLM | Os nós de inferência (`llama-server`) |
| UFES_Redes_Trab2_Frontend | O **cliente** web, servido pelo próprio gateway |

## Tecnologias Utilizadas

- **Linguagens:** Python 3.12 (servidor, cliente de terminal, experimentos) e JavaScript (cliente web, sem framework).
- **Bibliotecas:**
  - FastAPI e Uvicorn: HTTP e SSE;
  - asyncio: concorrência;
  - httpx: cliente HTTP com streaming;
  - Pydantic: validação de config e do JSON;
  - matplotlib: gráficos;
  - pytest e ruff: testes e lint.
- **Inferência:** llama.cpp `llama-server` (binário oficial b12211), com modelos GGUF Qwen3 1.7B e Qwen3.5 4B (Q4_K_M).
- **Rede e segurança:**
  - HTTP/1.1 com Server-Sent Events;
  - TLS no gateway (CA local);
  - token Bearer guardado como hash;
  - token bucket para o limite de taxa;
  - chave de API entre o gateway e os nós.

## Como Executar

### Requisitos

- Linux x86-64 ou Windows 10/11, com **Python 3.8 ou mais novo** (para o `lab.py`; ele mesmo traz o Python 3.12 se
  precisar).
- RAM: ~2 GB com um modelo (`--leve`) ou ~6 GB com os dois.
- `openssl` e `bash` para o TLS do gateway (presentes em qualquer Linux; no Windows, o Git for Windows traz os dois).
- Para desenvolvimento: as dependências Python em `requirements.txt` (que lê o `pyproject.toml`).

### Instruções de Execução

1. **Clone os três repositórios** na mesma pasta:

   ```bash
   git clone https://github.com/moinholigeiro/UFES_Redes_Trab2_Backend.git
   git clone https://github.com/moinholigeiro/UFES_Redes_Trab2_LLM.git
   git clone https://github.com/moinholigeiro/UFES_Redes_Trab2_Frontend.git
   cd UFES_Redes_Trab2_Backend
   ```

   No laboratório, sem credencial do GitHub, use o zip gerado por `python3 lab.py pacote` (ver
   [docs/LABORATORIO.md](docs/LABORATORIO.md)).

2. **Instale as dependências.** O `lab.py` faz isso sozinho no passo 3: cria o `.venv`, baixa o `llama-server` e os
   modelos e confere o SHA-256. Para instalar à mão:

   ```bash
   python3 -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Execute o servidor** (gateway + nós de inferência):

   ```bash
   python3 lab.py demo            # dois modelos; ou: python3 lab.py demo --leve   (um modelo, ~2 GB)
   ```

   No fim, ele imprime a URL (`https://127.0.0.1:8443`) e o token. `Ctrl+C` encerra tudo.

4. **Execute o cliente.** Escolha um dos dois:
   - **web:** abra `https://127.0.0.1:8443`, aceite o certificado da CA local e cole o token;
   - **terminal:**

     ```bash
     export LLM_GATEWAY_TOKEN="$(cat .lab/token)"
     .venv/bin/llm-gateway-client --url https://127.0.0.1:8443 --ca .lab/tls/ca.crt \
         --domain redes --input "O que é o three-way handshake do TCP?"
     ```

**Várias máquinas** (nós em outras máquinas, balanceamento, falha de nó): [docs/LABORATORIO.md](docs/LABORATORIO.md).

## Como Testar

| O quê | Como |
|---|---|
| Testes automatizados (~145, sem modelo, uns 3 min) | `pip install -r requirements.txt pytest pytest-asyncio` e depois `python -m pytest -q` |
| Lint | `ruff check src tests experiments lab.py` |
| Fila e posição | Com o `demo` no ar, abra 3 abas e envie ao mesmo tempo: a tela mostra a posição caindo |
| Segurança | Sem token → 401; domínio não autorizado → 403; acima do limite de taxa → 429; nó sem a chave → 401 do `llama-server` |
| Falha de nó | Cenário 5 do [docs/PLANO.md](docs/PLANO.md): `Ctrl+C` num nó durante a carga |
| Desempenho e estabilidade | `python3 lab.py experimento --desafio`: TTFT e vazão para N = 1…16 com previsão feita antes, e FIFO × curtos primeiro. Ensaio rápido sem modelo: `--simulado` |

O CI do GitHub Actions roda os testes e o lint a cada push.

## Funcionalidades Implementadas

**Núcleo (spec)**
- Protocolo `POST /v1/generate` com resposta token a token em SSE: `meta`, `queued`, `delta`, `result`, `done`,
  `error` ([contrato v1.1](contracts/public/v1/README.md)).
- Dois domínios com modelo, prompt e parâmetros próprios, roteados pelo domínio declarado.
- Fila por nó com limite de K vagas e fila limitada (503 quando lota), prazo total, cancelamento quando o cliente
  desconecta, e corte de cliente lento.
- Métricas: TTFT, tokens/s, latência fim a fim, vazão agregada (`GET /metrics`) e um log JSONL sem texto do pedido.

**Desempenho**
- Balanceamento: round-robin, menor fila e menor espera prevista ((fila + 1) × EWMA, com reamostragem).
- Failover:
  - antes do primeiro token, o pedido é refeito em outra réplica;
  - pedidos que esperavam na fila de um nó que caiu migram;
  - depois do primeiro token, o cliente recebe um erro parcial explícito.
- Política de fila: FIFO ou curtos primeiro com envelhecimento.

**Segurança**
- Token Bearer guardado como hash, autorização por domínio, limite de taxa por usuário (token bucket), TLS no gateway e
  chave de API entre gateway e nós.

**Inteligência (opcional, desligado)**
- Roteamento semântico piloto (`pip install -e .[router]`).

**Experimento**
- Gerador de carga em laço fechado, previsão pela lei de Little gravada antes de medir, repetições, IC 95% e gráficos.

**Operação**
- `lab.py`: demo, nó, gateway, experimento, baixar e pacote, num comando, com binário e modelos conferidos por SHA-256.

## Possíveis Melhorias Futuras

- Retomar a resposta em outro nó quando o nó cai **depois** do primeiro token. Hoje é erro parcial; com JSON forçado,
  a retomada não é trivial.
- Mais de um processo de gateway, com fila e limite de taxa compartilhados (por exemplo, em Redis).
- Exportar o prontuário como Bundle HL7 FHIR R4.
- Avaliar a qualidade da extração com um conjunto anotado (o AnonyMED-BR, se a licença permitir).
- Cache semântico e RAG com o material da disciplina (trilha Inteligência).
- Perfil com GPU.

## Documentação

| Documento | Conteúdo |
|---|---|
| [EXPLICACAO.md](EXPLICACAO.md) | Diagramas (repositórios, camadas, fluxo de um pedido, falha) e o código explicado; perguntas de entrevista |
| [docs/RELATORIO.pdf](docs/RELATORIO.pdf) ([.md](docs/RELATORIO.md)) | Relatório breve: as principais escolhas de implementação |
| [docs/ROTEIRO-E-APRESENTACAO.pdf](docs/ROTEIRO-E-APRESENTACAO.pdf) | **Roteiro de teste no laboratório e material da apresentação** (decisões, trade-offs, perguntas prováveis). Gerador: `docs/apresentacao/gerar_pdf.py` |
| [docs/PLANO.md](docs/PLANO.md) | Plano v2: requisitos, decisões D0–D19, cenários de máquinas |
| [docs/MUDANCAS.md](docs/MUDANCAS.md) | O que mudou em 09/11 e como conferir |
| [docs/LABORATORIO.md](docs/LABORATORIO.md) | Tutorial do laboratório |
| [experiments/README.md](experiments/README.md) | Experimento |
| [docs/ENUNCIADO.md](docs/ENUNCIADO.md) · [docs/INSTRUCOES-ENTREGA.pdf](docs/INSTRUCOES-ENTREGA.pdf) | Spec e instruções de entrega do professor |
| [CHANGELOG.md](CHANGELOG.md) | Histórico de mudanças |
