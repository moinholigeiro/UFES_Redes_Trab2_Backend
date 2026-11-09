# Tutorial do laboratório

Como rodar o T2 nas máquinas do laboratório de informática de forma **rápida, segura e igual em todas**. Tudo passa
por um comando, `python3 lab.py`, que fica neste repositório.

| Garantia | Como |
|---|---|
| Rápido | Um `unzip` e um comando. A primeira execução baixa o que falta; as seguintes sobem em segundos |
| Seguro | Sem senha do GitHub nas máquinas do laboratório. Nós LLM só aceitam pedidos com a chave do grupo; o gateway exige token e usa TLS |
| Consistente | Código, binário do `llama-server` e modelos fixados por commit e por SHA-256. Todas as máquinas rodam exatamente a mesma coisa |
| Limpo | Nada é instalado no sistema. `rm -rf t2-lab` desfaz tudo |

**Requisitos da máquina:** Linux x86-64 (ou Windows 10/11) com Python 3.8 ou mais novo. Se o Python for antigo ou não
tiver o módulo `venv`, o `lab.py` baixa o `uv`, que traz um Python 3.12 só para a pasta. RAM: ~2 GB com `--leve`, ~6 GB
com os dois modelos. Para o TLS do gateway, `openssl` e `bash` (presentes em qualquer Linux).

---

## Passo 1 — Em casa, uma vez: montar o pacote

Numa máquina **com acesso aos repositórios** (a de quem vai levar o pendrive), com os três repositórios lado a lado e
atualizados:

```bash
cd UFES_Redes_Trab2_Backend
python3 lab.py baixar --destino ../cache          # llama-server (Linux e Windows), uv e os 2 modelos (~4 GB)
python3 lab.py pacote --cache ../cache            # gera ../t2-lab.zip com tudo dentro
```

Copie o `t2-lab.zip` para um pendrive. Ele leva:

- **os três repositórios**, exatamente no commit atual (`git archive`); o `LEIA-ME.txt` lista os commits;
- **uma chave nova** em `UFES_Redes_Trab2_Backend/.lab/node-api-key`, igual em todas as máquinas que usarem este zip;
- **a pasta `cache/`**, com o binário e os modelos. O `lab.py` usa essa pasta sozinho e não baixa nada da internet.

Sem `--cache`, o zip fica com poucos MB, e cada máquina baixa binário e modelos na primeira execução.

> A chave do pacote é um segredo do grupo: não publique o zip. Para trocar a chave, gere outro pacote.

## Passo 2 — No laboratório: a demonstração numa máquina (cenário 1)

```bash
unzip t2-lab.zip
cd t2-lab/UFES_Redes_Trab2_Backend
python3 lab.py demo            # ou: python3 lab.py demo --leve   (máquina com 8 GB de RAM)
```

Na primeira vez, ele leva de 1 a 3 minutos: cria o ambiente Python, extrai o `llama-server`, confere os modelos e
carrega cada um na memória. No fim, imprime:

```text
==============================================================================
  T2 no ar.  Tela e API:  https://127.0.0.1:8443
  Token (cole na tela):    <token>
  Certificado da CA:       .../.lab/tls/ca.crt
  ...
==============================================================================
```

1. Abra `https://127.0.0.1:8443` no navegador. O aviso de certificado é esperado: ele foi assinado pela CA local do
   trabalho. Clique em **Avançado → Continuar**, ou importe o `ca.crt` no navegador.
2. Cole o token no campo **Token provisionado**.
3. Escolha o domínio, escreva a pergunta e clique em **Enviar**.
4. Para mostrar a fila, abra 3 abas e envie nas três ao mesmo tempo: a tela mostra "Posição na fila: 2º" diminuindo.

`Ctrl+C` no terminal encerra o gateway e os nós.

**O que fica exposto:** nada. Nós e gateway ouvem só em `127.0.0.1`.

## Passo 3 — Várias máquinas (cenários 2 a 5)

Use o **mesmo `t2-lab.zip`** em todas as máquinas, para que a chave seja a mesma. Anote o IP de cada máquina
(`hostname -I`).

**Em cada máquina LLM** (ex.: B = 10.0.0.5):

```bash
cd t2-lab/UFES_Redes_Trab2_Backend
python3 lab.py no --modelo pequeno                 # redes, porta 8101
python3 lab.py no --modelo grande                  # prontuário, porta 8102 (em outro terminal, se couber na RAM)
```

O nó ouve na rede do laboratório (`0.0.0.0`), mas **só responde a quem tiver a chave**. Sem ela, o `llama-server`
devolve 401. O `/health` continua aberto, sem expor nada.

**Na máquina do gateway** (A):

```bash
python3 lab.py gateway --nos redes=10.0.0.5:8101,prontuario=10.0.0.5:8102
```

Para abrir a tela a partir de outra máquina, acrescente `--publico`. O gateway passa a ouvir na LAN, sempre com TLS e
token.

| Cenário | Comandos |
|---|---|
| 2 — gateway e LLM separados | B: `lab.py no --modelo pequeno`; A: `lab.py gateway --nos redes=IP_B:8101` |
| 3 — N clientes (experimento) | A: `lab.py gateway --nos redes=IP_B:8101 --experimento`; C: `lab.py experimento --url https://IP_A:8443 --ca ca.crt --token-file token --k 1` (copie de A para C o `ca.crt` que o gateway imprime em "Certificado da CA" e o `.lab/token`) |
| 4 — balanceamento | B: `lab.py no --modelo pequeno --threads 8`; D: `lab.py no --modelo pequeno --threads 2`; A: `lab.py gateway --nos redes=IP_B:8101,redes=IP_D:8101 --balanceamento least_latency` (repita com `round_robin` e `least_loaded`) |
| 5 — falha de nó | Cenário 4 com carga rodando; `Ctrl+C` no terminal da máquina D |

**Vagas por nó (K).** O `--slots` do nó e o `--k` do gateway precisam ser iguais: `lab.py no --slots 2` e
`lab.py gateway --k 2`.

## Passo 4 — O experimento

Numa máquina só, com o `lab.py` controlando tudo (ele sobe e desce os nós para cada K e cada política):

```bash
python3 lab.py experimento --desafio
```

Ordem do que ele faz:
1. para cada K (padrão 1 e 2), sobe o nó com K vagas;
2. calibra com N = K e **grava a previsão** (`previsao-k*.json`) antes de medir;
3. roda N = 1, 2, 4, 8, 16, com 3 repetições de 20 pedidos cada (mais os N primeiros, descartados como transitório);
4. roda a pergunta-desafio: N = 8, metade dos pedidos curtos, FIFO contra curtos primeiro;
5. gera os gráficos e o `resumo.md` em `experiments/resultados/<data>/`.

**Tempo estimado na CPU** (Qwen3 1.7B, ~16 s por pedido de 128 tokens): ~3 a 4 h com os padrões. Para caber numa
tarde, use `--k 1 --reps 2` (~1 h). O `LEIA-ME.txt` da pasta registra o comando usado.

**Ensaio sem modelo, em 5 minutos:** `python3 lab.py experimento --simulado --reps 2 --pedidos 10`. Serve para
conferir o caminho inteiro (carga, previsão, gráficos) antes de gastar horas. A pasta ganha o sufixo `_simulado`,
fica fora do git, e **não é resultado do trabalho**.

## Solução de problemas

| Sintoma | Causa provável | O que fazer |
|---|---|---|
| `não consegui baixar ...` | Sem internet ou proxy do laboratório | Use o pacote com `--cache` (passo 1) |
| `SHA-256 de ... não confere` | Download corrompido | Rode de novo: o arquivo parcial é descartado |
| `redes-1 terminou com código ...` | Falta RAM, ou porta em uso | Veja `.lab/logs/redes-1.log`; use `--leve` ou feche o processo na porta |
| `gateway não respondeu` | Erro de configuração | Veja `.lab/logs/gateway.log` |
| O navegador recusa a página | Certificado da CA local | Avançado → Continuar, ou importe `.lab/tls/ca.crt` |
| 401 na tela | Token errado | Copie o token impresso no fim do `lab.py demo` (também em `.lab/token`) |
| Nó de outra máquina sempre "fora do ar" | Firewall ou chave diferente | `curl http://IP:8101/health` precisa responder; use o mesmo zip nas duas máquinas |
| Experimento lento demais | CPU | `--max-tokens 64`, `--reps 3`, `--pedidos 15` |

**Onde fica cada coisa** (tudo dentro de `UFES_Redes_Trab2_Backend/.lab/`, fora do git):

| Arquivo | O que é |
|---|---|
| `token`, `users.toml` | Token de acesso e o hash dele |
| `node-api-key` | Chave entre gateway e nós |
| `tls/` | CA local e certificado do gateway |
| `gateway.toml`, `nos/*.toml` | Configurações geradas (não edite: rode o `lab.py` de novo) |
| `logs/` | Log de cada processo e o `requests.jsonl` do gateway |

Para recomeçar do zero numa máquina: `rm -rf .lab .venv`.
