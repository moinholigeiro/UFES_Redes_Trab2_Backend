"""Gera docs/ROTEIRO-E-APRESENTACAO.pdf: roteiro de teste no lab e material da apresentação.

Uso (Windows, usa as fontes Arial/Consolas do sistema):
    pip install reportlab matplotlib
    python docs/apresentacao/gerar_pdf.py

Para trocar o gráfico do ensaio simulado pelo resultado real, edite `grafico_ensaio()` com os números
do `experiments/resultados/<data>/resumo.md` (ou aponte para o PNG gerado pelo graficos.py).
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from reportlab.graphics.shapes import Drawing, Line, Polygon, Rect, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

AQUI = Path(__file__).resolve().parent
SAIDA = AQUI.parent / "ROTEIRO-E-APRESENTACAO.pdf"

F = r"C:\Windows\Fonts"
pdfmetrics.registerFont(TTFont("Arial", rf"{F}\arial.ttf"))
pdfmetrics.registerFont(TTFont("Arial-B", rf"{F}\arialbd.ttf"))
pdfmetrics.registerFont(TTFont("Arial-I", rf"{F}\ariali.ttf"))
pdfmetrics.registerFont(TTFont("Mono", rf"{F}\consola.ttf"))
pdfmetrics.registerFont(TTFont("Simbolo", rf"{F}\seguisym.ttf"))
pdfmetrics.registerFontFamily("Arial", normal="Arial", bold="Arial-B", italic="Arial-I", boldItalic="Arial-B")

AZUL = colors.HexColor("#1f4e79")
VERDE = colors.HexColor("#d9f2e3")
VERDE_B = colors.HexColor("#1d7a4d")
AMARELO = colors.HexColor("#fff3cd")
AMARELO_B = colors.HexColor("#a07800")
CINZA = colors.HexColor("#f2f4f7")
CINZA_B = colors.HexColor("#c9d1db")

st = {
    "titulo": ParagraphStyle("titulo", fontName="Arial-B", fontSize=22, leading=27, textColor=AZUL,
                             alignment=TA_CENTER, spaceAfter=6),
    "sub": ParagraphStyle("sub", fontName="Arial", fontSize=11, leading=15, alignment=TA_CENTER,
                          textColor=colors.HexColor("#444444")),
    "h1": ParagraphStyle("h1", fontName="Arial-B", fontSize=16, leading=20, textColor=AZUL, spaceBefore=4,
                         spaceAfter=8),
    "h2": ParagraphStyle("h2", fontName="Arial-B", fontSize=12, leading=15, textColor=AZUL, spaceBefore=10,
                         spaceAfter=4),
    "p": ParagraphStyle("p", fontName="Arial", fontSize=9.5, leading=13, spaceAfter=4),
    "pequeno": ParagraphStyle("pequeno", fontName="Arial", fontSize=8.5, leading=11),
    "cel": ParagraphStyle("cel", fontName="Arial", fontSize=8.5, leading=11),
    "celb": ParagraphStyle("celb", fontName="Arial-B", fontSize=8.5, leading=11, textColor=colors.white),
    "code": ParagraphStyle("code", fontName="Mono", fontSize=8.3, leading=10.5, backColor=CINZA,
                           borderColor=CINZA_B, borderWidth=0.5, borderPadding=5, leftIndent=5, rightIndent=5,
                           spaceBefore=3, spaceAfter=8),
    "aviso": ParagraphStyle("aviso", fontName="Arial", fontSize=9, leading=12, backColor=AMARELO,
                            borderColor=AMARELO_B, borderWidth=0.6, borderPadding=6, leftIndent=6, rightIndent=6,
                            spaceBefore=4, spaceAfter=10),
}


def P(texto, estilo="p"):
    return Paragraph(texto, st[estilo])


def codigo(texto):
    return Preformatted(texto.strip("\n"), st["code"])


def tabela(cabecalho, linhas, larguras, destaque_primeira_coluna=False):
    dados = [[P(c, "celb") for c in cabecalho]]
    for linha in linhas:
        dados.append([P(c, "cel") for c in linha])
    t = Table(dados, colWidths=[w * cm for w in larguras], repeatRows=1)
    estilo = [
        ("BACKGROUND", (0, 0), (-1, 0), AZUL),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.4, CINZA_B),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, CINZA]),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    t.setStyle(TableStyle(estilo))
    return t


# ---------------------------------------------------------------------------------------------- diagramas


def caixa(d, x, y, w, h, linhas, fill=VERDE, borda=VERDE_B, negrito_primeira=True, tam=8):
    d.add(Rect(x, y, w, h, fillColor=fill, strokeColor=borda, strokeWidth=1, rx=4, ry=4))
    total = len(linhas) * (tam + 2)
    yy = y + h / 2 + total / 2 - tam
    for i, texto in enumerate(linhas):
        fonte = "Arial-B" if (i == 0 and negrito_primeira) else "Arial"
        d.add(String(x + w / 2, yy, texto, fontName=fonte, fontSize=tam, textAnchor="middle"))
        yy -= tam + 2


def seta(d, x1, y1, x2, y2, rotulo=None, dy=4, cor=colors.HexColor("#333333")):
    d.add(Line(x1, y1, x2, y2, strokeColor=cor, strokeWidth=1))
    import math

    ang = math.atan2(y2 - y1, x2 - x1)
    a = 6
    p1 = (x2 - a * math.cos(ang - 0.4), y2 - a * math.sin(ang - 0.4))
    p2 = (x2 - a * math.cos(ang + 0.4), y2 - a * math.sin(ang + 0.4))
    d.add(Polygon([x2, y2, p1[0], p1[1], p2[0], p2[1]], fillColor=cor, strokeColor=cor))
    if rotulo:
        for i, linha in enumerate(rotulo.split("\n")):
            d.add(String((x1 + x2) / 2, (y1 + y2) / 2 + dy - i * 9, linha, fontName="Arial", fontSize=7,
                         textAnchor="middle", fillColor=colors.HexColor("#333333")))


def diagrama_arquitetura():
    d = Drawing(17 * cm, 6.3 * cm)
    caixa(d, 5, 70, 100, 60, ["Clientes", "tela web", "cliente de terminal", "gerador de carga"], fill=AMARELO,
          borda=AMARELO_B)
    caixa(d, 165, 20, 150, 140, ["Gateway (Backend)", "asyncio, 1 processo", "segurança: token, domínio,",
                                 "limite de taxa, TLS", "fila por nó (K vagas)", "FIFO ou curtos primeiro",
                                 "balanceador (3 políticas)", "failover · métricas", "valida o JSON"])
    caixa(d, 375, 110, 105, 50, ["llama-server", "Qwen3 1.7B", "redes (réplica 1)"])
    caixa(d, 375, 55, 105, 45, ["llama-server", "Qwen3 1.7B", "redes (réplica 2)"])
    caixa(d, 375, 0, 105, 45, ["llama-server", "Qwen3.5 4B", "prontuário"])
    seta(d, 105, 100, 165, 100, "HTTPS + SSE\ntoken Bearer", dy=10)
    seta(d, 315, 125, 375, 135, "HTTP + chave", dy=8)
    seta(d, 315, 90, 375, 78)
    seta(d, 315, 55, 375, 22)
    d.add(String(395, 168, "repo LLM (nós)", fontName="Arial-I", fontSize=7))
    d.add(String(185, 168, "repo Backend", fontName="Arial-I", fontSize=7))
    d.add(String(12, 138, "repo Frontend (tela)", fontName="Arial-I", fontSize=7))
    return d


def diagrama_lab():
    d = Drawing(17 * cm, 5.4 * cm)
    caixa(d, 5, 40, 150, 95, ["PC-A", "gateway :8443 (TLS)", "tela web", "gerador de carga",
                              "Wireshark"], fill=AMARELO, borda=AMARELO_B)
    caixa(d, 300, 110, 175, 40, ["PC-B", "nó redes (rápido) :8101"])
    caixa(d, 300, 60, 175, 40, ["PC-C", "nó redes (lento, --threads 2) :8101"])
    caixa(d, 300, 10, 175, 40, ["PC-D", "nó prontuário (4B) :8102"])
    seta(d, 155, 110, 300, 130, "HTTP + chave de API (LAN)", dy=10)
    seta(d, 155, 88, 300, 80)
    seta(d, 155, 66, 300, 30)
    d.add(String(80, 25, "outros PCs abrem https://IP_A:8443", fontName="Arial-I", fontSize=7,
                 textAnchor="middle"))
    return d


def grafico_ensaio():
    # Ensaio simulado de 09/11 (Ubuntu 24.04, nó simulado): médias de 2 repetições, IC 95%.
    n = [1, 2, 4, 8, 16]
    k1_med, k1_ic = [0.25, 1.26, 3.32, 7.50, 15.74], [0.00, 0.01, 0.22, 0.25, 0.65]
    k1_prev = [0.25, 1.33, 3.50, 7.85, 16.54]
    k2_med, k2_ic = [0.23, 0.23, 1.26, 3.32, 7.53], [0.03, 0.05, 0.04, 0.07, 0.65]
    k2_prev = [0.27, 0.27, 1.36, 3.56, 7.94]
    fig, ax = plt.subplots(figsize=(6.4, 3.3))
    ax.errorbar(n, k1_med, yerr=k1_ic, marker="o", capsize=3, label="medido K=1", color="#1f77b4")
    ax.plot(n, k1_prev, "--", label="previsto K=1", color="#1f77b4", alpha=0.6)
    ax.errorbar(n, k2_med, yerr=k2_ic, marker="s", capsize=3, label="medido K=2", color="#2ca02c")
    ax.plot(n, k2_prev, "--", label="previsto K=2", color="#2ca02c", alpha=0.6)
    ax.set_xscale("log", base=2)
    ax.set_xticks(n, [str(x) for x in n])
    ax.set_xlabel("clientes simultâneos (N)")
    ax.set_ylabel("TTFT (s)")
    ax.set_title("Ensaio simulado: TTFT medido × previsto (lei de Little)", fontsize=10)
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=8)
    fig.tight_layout()
    caminho = AQUI / "ensaio.png"  # temporário; fica fora do git
    fig.savefig(caminho, dpi=200)
    plt.close(fig)
    return caminho


# ---------------------------------------------------------------------------------------------- conteúdo


def rodape(canvas, doc):
    canvas.saveState()
    canvas.setFont("Arial", 7.5)
    canvas.setFillColor(colors.HexColor("#777777"))
    canvas.drawString(2 * cm, 1.2 * cm, "T2 Redes de Computadores (INF16158) · UFES · Daniel, Lívia e Eduardo")
    canvas.drawRightString(A4[0] - 2 * cm, 1.2 * cm, f"página {doc.page}")
    canvas.restoreState()


def montar():
    h = []
    # ---- capa
    h += [Spacer(1, 3 * cm), P("T2 — Gateway distribuído de LLMs abertos", "titulo"),
          P("Roteiro de teste no laboratório e preparação para a apresentação", "sub"), Spacer(1, 0.4 * cm),
          P("Redes de Computadores (INF16158) · UFES · Prof. Magnos Martinello<br/>"
            "Equipe: Daniel, Lívia e Eduardo · entrega: <b>22/11/2026</b>", "sub"), Spacer(1, 1.2 * cm)]
    h.append(tabela(["Parte", "Conteúdo", "Pág."], [
        ["1", "Roteiro de teste no laboratório (4 PCs)", "2"],
        ["2", "O sistema em uma página", "4"],
        ["3", "Decisões técnicas e trade-offs (o coração da apresentação)", "5"],
        ["4", "Fila, concorrência e o experimento", "6"],
        ["5", "Falhas, erros e segurança", "8"],
        ["6", "Perguntas prováveis do professor", "9"],
        ["7", "Roteiro de fala (~10 min) e checklist do dia", "10"],
        ["8", "Solução de problemas na rede local (para consertar durante a apresentação)", "11"],
    ], [1.5, 13, 1.5]))
    h += [Spacer(1, 0.8 * cm), P(
        "<b>Por que este material:</b> pelas instruções de entrega, <b>40 dos 100 pontos</b> são "
        "\"conhecimento sobre o código\". O professor quer ouvir <b>por que</b> escolhemos cada coisa e o que "
        "perdemos com ela. Cada um dos três precisa saber explicar todas as partes.", "aviso"),
          PageBreak()]

    # ---- parte 1: roteiro
    h.append(P("1. Roteiro de teste no laboratório", "h1"))
    h.append(P("<b>Antes do lab (em casa, UMA pessoa).</b> Com os 3 repositórios lado a lado e atualizados "
               "(<font name='Mono'>git pull</font> nos três):"))
    h.append(codigo("""
cd UFES_Redes_Trab2_Backend
python3 lab.py pacote                           # ../t2-lab.zip (< 1 MB): código + UMA chave
python3 lab.py baixar --destino ../cache --sistema todos   # binário + modelos (~4 GB) -> pendrive
"""))
    h.append(P("<b>Regra de ouro: um único pacote para todos.</b> Cada <font name='Mono'>lab.py pacote</font> cria "
               "uma chave nova; PCs com zips de pacotes diferentes dão <b>401 \"nó recusou a chave de API\"</b> "
               "(aconteceu no teste de 19/11). Quem gerou o pacote <b>manda o mesmo t2-lab.zip por e-mail aos "
               "três</b> e ninguém gera outro até a apresentação. O cache de ~4 GB vai no pendrive e é copiado "
               "para <font name='Mono'>t2-lab/cache/</font> em cada PC.", "aviso"))
    h.append(P("Papéis", "h2"))
    h.append(diagrama_lab())
    h.append(P("<b>Passo 0, em todos os PCs:</b> descompactar o <b>mesmo</b> zip, copiar o cache do pendrive, "
               "anotar o IP e conferir que a impressão da chave é <b>igual em todos</b>.", "p"))
    h.append(codigo("""
unzip t2-lab.zip && cp -r /media/<pendrive>/cache t2-lab/ && cd t2-lab/UFES_Redes_Trab2_Backend
hostname -I          # use 192.168.112.x ou 10.9.12.x; 192.168.122.x é rede virtual, não serve
python3 lab.py chave # os 12 dígitos têm que ser iguais em todos os PCs
"""))
    h.append(P("Testes", "h2"))
    h.append(tabela(["#", "Onde", "Comando", "O que conferir"], [
        ["1", "PC-A", "<font name='Mono'>python3 lab.py demo --leve</font>",
         "Abrir https://127.0.0.1:8443, aceitar o certificado, colar o token. 3 abas enviando juntas: "
         "\"Posição na fila: 2º\" caindo."],
        ["2", "PC-B / PC-D / PC-A",
         "B: <font name='Mono'>lab.py no --modelo pequeno</font><br/>D: <font name='Mono'>lab.py no --modelo "
         "grande</font><br/>A: <font name='Mono'>curl http://IP_B:8101/health</font> (tem que dar "
         "<i>status ok</i>)<br/>A: <font name='Mono'>lab.py gateway --publico --nos "
         "redes=IP_B:8101,prontuario=IP_D:8102</font>",
         "De outro PC, abrir https://IP_A:8443. Os dois domínios respondem. Wireshark em A com "
         "<font name='Mono'>tcp.port == 8101</font>: print do handshake e do stream."],
        ["3", "PC-C / PC-A",
         "C: <font name='Mono'>lab.py no --modelo pequeno --threads 2</font><br/>A: gateway com "
         "<font name='Mono'>--nos redes=IP_B:8101,redes=IP_C:8101 --balanceamento least_latency</font><br/>"
         "A: <font name='Mono'>lab.py experimento --url https://127.0.0.1:8443 --ca &lt;ca.crt&gt; "
         "--token-file .lab/token --k 1 --clientes 8 --reps 1</font>",
         "Repetir com <font name='Mono'>round_robin</font> e <font name='Mono'>least_loaded</font>. "
         "Comparar quantos pedidos cada nó fez (<font name='Mono'>/metrics</font>) e o TTFT."],
        ["4", "PC-C", "Com a carga do teste 3 rodando: <b>Ctrl+C</b>",
         "Pedidos na fila de C terminam em B. Quem já recebia texto de C recebe erro parcial. "
         "<font name='Mono'>/metrics</font>: C com <i>healthy: false</i>."],
        ["5", "PC livre, sozinho", "<font name='Mono'>python3 lab.py experimento --desafio</font>",
         "~3 a 4 h (ou <font name='Mono'>--k 1 --reps 2</font>, ~1 h). Copiar "
         "<font name='Mono'>experiments/resultados/&lt;data&gt;/</font> para o pendrive."],
    ], [0.6, 2.2, 7.2, 7.0]))
    h.append(P("O caminho do <font name='Mono'>ca.crt</font> é impresso pelo gateway na linha \"Certificado da "
               "CA\". O teste 5 deve rodar <b>sem nada mais pesado na mesma máquina</b>.", "pequeno"))
    h.append(P("Se der problema: <b>parte 8</b> (pág. 11), com diagnóstico em 4 comandos e as correções.", "h2"))
    h.append(KeepTogether([tabela(["Sintoma rápido", "O que fazer"], [
        ["Erro ao subir", "Ler <font name='Mono'>.lab/logs/&lt;nome&gt;.log</font>"],
        ["<font name='Mono'>curl</font> no nó não responde de outro PC",
         "Firewall do lab: apresentar com o teste 1 (tudo num PC) e explicar o desenho distribuído pelo diagrama"],
        ["Porta ocupada", "Rodar o comando de novo: o lab.py encerra o que sobrou da execução anterior"],
        ["Pouca RAM", "<font name='Mono'>--leve</font> (um modelo, ~2 GB)"],
        ["Navegador recusa a página", "Avançado → Continuar (é a CA local do trabalho)"],
        ["Recomeçar do zero", "<font name='Mono'>rm -rf .lab .venv</font>"],
    ], [6, 11])]))
    h.append(Spacer(1, 0.3 * cm))
    h.append(P("<b>Prontuário:</b> usar o modelo grande (PC-D). No teste com o modelo pequeno o JSON veio "
               "válido, mas com campos trocados.", "aviso"))
    h.append(PageBreak())

    # ---- parte 2: sistema
    h.append(P("2. O sistema em uma página", "h1"))
    h.append(P("<b>Em uma frase:</b> um gateway que coloca cada pedido na fila do nó de IA certo e devolve a "
               "resposta aos poucos, com modelos abertos rodando nas nossas máquinas. A tese do Projeto 1: "
               "<b>um serviço de IA é um problema de filas, roteamento e transporte</b>."))
    h.append(diagrama_arquitetura())
    h.append(P("Os dois domínios", "h2"))
    h.append(tabela(["Domínio", "Modelo", "Saída", "Parâmetros"], [
        ["<b>redes</b>: assistente da disciplina", "Qwen3 1.7B (Q4_K_M)", "texto livre",
         "temperatura 0,7 (0 no experimento)"],
        ["<b>prontuario</b>: extração de prontuário sintético", "Qwen3.5 4B (Q4_K_M)",
         "JSON validado (idade, sexo, queixa, diagnósticos, medicamentos, alergias, sinais vitais)",
         "temperatura 0, JSON Schema"],
    ], [4.5, 3.2, 5.8, 3.5]))
    h.append(P("Um pedido, passo a passo (eventos SSE)", "h2"))
    h.append(tabela(["#", "Quem", "O que acontece"], [
        ["1", "Cliente → gateway", "<font name='Mono'>POST /v1/generate {domain, input}</font> + token, por HTTPS"],
        ["2", "Gateway", "Confere TLS, token, domínio permitido e limite de taxa; valida o corpo"],
        ["3", "Gateway", "Balanceador escolhe o nó; o pedido entra na fila. Envia <b>meta</b> e "
                         "<b>queued {position}</b>; a posição é atualizada sempre que a fila anda"],
        ["4", "Gateway → nó", "Quando há vaga: <font name='Mono'>POST /v1/chat/completions</font> em streaming, "
                              "com a chave de API"],
        ["5", "Gateway → cliente", "Cada trecho gerado vira um evento <b>delta</b> (o primeiro marca o TTFT)"],
        ["6", "Gateway → cliente", "Prontuário: valida o JSON e envia <b>result</b>. Sempre termina com "
                                   "<b>done</b> (tokens, motivo do fim) ou <b>error</b>: exatamente um"],
    ], [0.6, 3.4, 13]))
    h.append(P("Onde fica o estado: <b>não há banco de dados</b>. Filas e limites ficam na memória do gateway "
               "(um processo); o disco guarda só um log JSONL por tentativa (sem texto do pedido) e o hash dos "
               "tokens.", "pequeno"))
    h.append(PageBreak())

    # ---- parte 3: decisões
    h.append(P("3. Decisões técnicas e trade-offs", "h1"))
    h.append(P("Para cada decisão: o que escolhemos, o que descartamos, <b>por quê</b> e <b>o que perdemos</b>. "
               "É esta tabela que o professor vai cobrar."))
    h.append(tabela(["Decisão", "Alternativa descartada", "Por quê", "O que perdemos (trade-off)"], [
        ["<b>Cliente-servidor</b> com gateway central", "P2P",
         "O modelo fica em poucos nós pesados; um ponto único faz autenticação, fila e métricas",
         "O gateway é ponto único de falha (mitigado nos nós, não no gateway)"],
        ["<b>TCP</b>", "UDP", "Um token perdido corrompe texto ou JSON; atraso de ms não atrapalha a leitura",
         "Retransmissão e controle de congestionamento custam um pouco de latência"],
        ["<b>SSE</b> sobre HTTPS", "WebSocket, gRPC",
         "Fluxo de mão única; é HTTP comum (proxy, TLS, curl); cancelar = fechar a conexão",
         "Sem canal do cliente para o servidor no meio do stream (não precisamos)"],
        ["<b>Event loop</b> (asyncio), 1 processo", "Uma thread por cliente; vários processos",
         "O gateway só espera rede; a CPU pesada está nos nós. Sem travas entre threads",
         "Filas em memória: reiniciar o gateway perde as filas; não escala horizontalmente"],
        ["<b>Fila por nó com K vagas</b>", "Um pedido por vez; todos em paralelo",
         "Todos juntos dividem a CPU e pioram o TTFT de todos; um por vez desperdiça o nó",
         "K precisa ser medido; acima de K+fila, recusamos com 503"],
        ["<b>Posição na fila</b> para o cliente", "Só manter a conexão viva",
         "Quem espera sabe onde está; é o dado da pergunta-desafio", "Mais eventos na conexão"],
        ["<b>FIFO ou curtos primeiro</b> + envelhecimento", "Só FIFO",
         "Curtos primeiro baixa a espera média; o envelhecimento impede que um longo espere para sempre",
         "Curtos primeiro piora a cauda (p95) dos pedidos longos"],
        ["<b>Menor espera prevista</b> = (fila+1) × EWMA", "Só olhar a latência média",
         "Considera a fila e reexamina o nó esquecido a cada 20 decisões",
         "EWMA reage com atraso a mudanças bruscas"],
        ["<b>Failover</b>: migra a fila; refaz antes do 1º token; erro parcial depois",
         "Continuar a resposta em outro nó",
         "Continuar não funciona com JSON forçado e o resultado não é verificável",
         "Quem já recebia texto precisa reenviar o pedido"],
        ["<b>JSON restrito por schema</b> + validação", "Pedir JSON no prompt",
         "O runtime só gera JSON que cabe no schema; o gateway valida de novo",
         "Validar a forma não garante o conteúdo (vimos campos trocados no modelo pequeno)"],
        ["<b>Chave de API</b> entre gateway e nós", "HTTPS com certificado por nó",
         "Impede que outro aluno use nosso nó; muito mais simples de montar no lab",
         "Tráfego interno na LAN fica legível (aceitável: dados sintéticos; bom para o Wireshark)"],
        ["<b>lab.py</b> (um comando)", "Docker Compose; Nix",
         "O lab não tem Docker/Nix garantidos; só precisa de Python 3.8+; binário e modelos fixados por SHA-256",
         "Um script nosso para manter (testado em Linux e Windows)"],
        ["<b>Roteador semântico desligado</b>", "Deixar ligado",
         "A spec pede 2 trilhas (Desempenho e Segurança); o piloto tinha 120 frases sintéticas",
         "A trilha Inteligência fica como opcional"],
    ], [3.6, 3.0, 5.5, 4.9]))
    h.append(PageBreak())

    # ---- parte 4: fila e experimento
    h.append(P("4. Fila, concorrência e o experimento", "h1"))
    h.append(P("Como o gateway atende vários clientes", "h2"))
    h.append(P("Um <b>event loop</b> (asyncio) num único processo: enquanto um pedido espera a rede (o cliente ou o "
               "nó), o loop atende outro. Cada nó tem uma fila (<font name='Mono'>deque</font>) e K vagas. A conta "
               "\"tem vaga?\" e a reserva da vaga acontecem <b>sem pausa entre elas</b> (sem <font name='Mono'>await"
               "</font>): no event loop nada intercala ali, por isso o limite nunca é ultrapassado, sem precisar de "
               "trava."))
    h.append(P("O modelo de fila (a previsão, feita antes de medir)", "h2"))
    h.append(tabela(["Símbolo", "Significado"], [
        ["N", "clientes em laço fechado (cada um manda o próximo pedido assim que recebe o done)"],
        ["K", "vagas do nó (pedidos gerando ao mesmo tempo)"],
        ["S, T0", "tempo de um pedido e TTFT sem fila, medidos na calibração (N = K)"],
    ], [2.5, 14.5]))
    h.append(P("Vazão máxima X = K/S. Lei de Little: R = N/X = N·S/K. Quem chega espera R − S na fila, então "
               "<b>para N &gt; K: TTFT ≈ (N/K − 1)·S + T0</b>; para N ≤ K, TTFT ≈ T0. O TTFT \"dispara\" em N = K e "
               "depois cresce em linha reta; a vazão agregada fica plana."))
    h.append(Image(str(grafico_ensaio()), width=13 * cm, height=6.7 * cm))
    h.append(P("<b>Ensaio simulado</b> (nó sem modelo, 09/11): valida que as ferramentas medem o que dizem; "
               "<b>não é o resultado</b>. Medido a menos de 5% do previsto.",
               "pequeno"))
    h.append(P("No laboratório (19/11): Qwen3 1.7B no PC-B, gateway no PC-A, K = 1", "h2"))
    h.append(tabela(["Medida", "Valor", "O que mostra"], [
        ["Geração por pedido", "15,5 · 14,4 · 12,2 tokens/s", "Estável, 2 a 3× a velocidade de leitura"],
        ["Prompt do 2º pedido", "0,97 s → 0,25 s", "Cache de prefixo do llama-server (só 20 tokens novos)"],
        ["3º cliente na fila (3 abas juntas)", "TTFT 54,3 s; fim a fim 73,3 s; 231 tokens",
         "Esperou 2 atendimentos inteiros: TTFT ≈ (N/K − 1)·S + T0 com S ≈ 26 s"],
    ], [5, 5.5, 6.5]))
    h.append(P("O que o ensaio pegou (bom exemplo para a apresentação)", "h2"))
    h.append(tabela(["Problema", "Causa", "Correção"], [
        ["A fila travou depois de uma rodada de carga",
         "Cliente desconectou no instante em que o pedido ganhou a vaga; a tarefa foi cancelada antes de começar "
         "e o <font name='Mono'>finally</font> que libera a vaga nunca rodou (bug de 02/11)",
         "Callback no fim da tarefa libera a vaga; teste de regressão"],
        ["N = 16 media 6 s, a previsão dizia 16 s",
         "Execuções curtas: só concluíam os pedidos que esperaram pouco (viés de sobrevivência)",
         "Descartar a primeira leva de N pedidos (regime estável)"],
    ], [4.5, 7.5, 5]))
    h.append(KeepTogether([P("Pergunta-desafio: TTFT ou tokens/s?", "h2"), P("Uma pessoa lê ~4 a 7 tokens/s. Se cada pedido gera mais rápido que isso, mais tokens/s não muda o "
               "que o usuário sente: <b>o que pesa é o TTFT</b>, a espera até a primeira palavra. No lab, o 3º cliente "
               "esperou 54 s pela primeira palavra e leu a resposta inteira em 19 s. No ensaio com 8 "
               "clientes e metade dos pedidos curtos, <b>curtos primeiro</b> baixou o TTFT médio de 10,5 s para "
               "5,4 s, mas o p95 subiu de 11,0 s para 17,3 s: os longos pagam pela espera menor dos curtos.")]))
    h.append(PageBreak())

    # ---- parte 5: falhas, erros, segurança
    h.append(P("5. Falhas, erros e segurança", "h1"))
    h.append(P("Quando um nó cai", "h2"))
    h.append(tabela(["Situação do pedido", "O que acontece", "Por quê"], [
        ["Esperando na fila do nó", "Migra para outra réplica do mesmo modelo", "Não começou: não há nada a perder"],
        ["No nó, antes do 1º token", "Refeito em outra réplica; o cliente recebe um novo meta",
         "Ainda não mostramos nada ao usuário"],
        ["Já recebendo texto", "error com partial = true, sem done",
         "Não emendamos respostas de nós diferentes"],
        ["O nó", "Sai da rotação até o /health voltar (checado a cada 2 s)", "Não mandar pedido para nó morto"],
    ], [4.5, 6.5, 6]))
    h.append(P("Erros tratados", "h2"))
    h.append(tabela(["Situação", "Resposta"], [
        ["Corpo inválido / grande demais / lento", "422 / 413 / 408, antes de entrar na fila"],
        ["Sem token / token errado / domínio proibido / acima da taxa", "401 / 401 / 403 / 429 com Retry-After"],
        ["Fila cheia / nenhum nó saudável", "503 com Retry-After"],
        ["Cliente desconecta ou é lento demais para ler", "Pedido cancelado e vaga liberada / client_too_slow"],
        ["Nó manda protocolo inválido", "backend_protocol_error (sem [DONE], dados depois do fim, etc.)"],
        ["JSON inválido ou cortado", "schema_invalid / truncated, sem result"],
        ["Prazo total do pedido", "deadline_exceeded (na fila ou gerando)"],
    ], [8, 9]))
    h.append(P("Segurança em camadas", "h2"))
    h.append(tabela(["Camada", "Como", "Protege contra"], [
        ["TLS (cliente ↔ gateway)", "Certificado de uma CA local gerada pelo lab.py",
         "Ler ou alterar o token e o conteúdo no caminho"],
        ["Token Bearer", "Guardado só como hash SHA-256; comparação em tempo constante", "Uso por quem não é da equipe"],
        ["Autorização por domínio", "Cada token lista os domínios permitidos", "Usuário acessar domínio que não deve"],
        ["Limite de taxa", "Token bucket por usuário (fichas por minuto + rajada)", "Um usuário monopolizar o serviço"],
        ["Chave de API nos nós", "llama-server --api-key-file; /health continua aberto",
         "Outro aluno do lab usar nosso nó"],
        ["Dados", "Só prontuários sintéticos; log sem texto do pedido", "Vazamento de dado de saúde (LGPD)"],
    ], [4, 7, 6]))
    h.append(PageBreak())

    # ---- parte 6: perguntas
    h.append(P("6. Perguntas prováveis do professor", "h1"))
    h.append(tabela(["Pergunta", "Resposta curta", "Onde no código"], [
        ["Por que SSE e não WebSocket?", "O fluxo é de mão única; SSE é HTTP comum e cancelar é fechar a conexão",
         "api.py, _event_stream"],
        ["Por que TCP e não UDP?", "Perder um token corrompe o texto/JSON; atraso de ms não atrapalha", "—"],
        ["Threads ou event loop?", "Event loop num worker: o gateway só espera rede; o pesado está nos nós",
         "api.py, cli.py"],
        ["10 clientes e 1 vaga: o que acontece?", "1 gera, 9 esperam na fila e recebem a posição; lotou: 503",
         "scheduler.py"],
        ["Como garantem o limite de vagas?", "Conta e reserva sem await entre elas: nada intercala no event loop",
         "scheduler.admit"],
        ["E se o cliente desconectar?", "O pedido é cancelado e a vaga liberada, inclusive no caso do bug que "
                                        "achamos", "scheduler._release_if_never_ran"],
        ["Nó cai antes / durante / depois?", "Fila migra; refaz antes do 1º token; erro parcial depois",
         "gateway.py"],
        ["Como medem TTFT? Trecho é token?", "Do envio ao 1º delta. Um delta pode ter vários tokens; a contagem "
                                             "vem do runtime, no done", "jobs.py"],
        ["Por que o TTFT dispara em N = K?", "Lei de Little em laço fechado: (N/K − 1)·S de espera",
         "experiments/previsao.py"],
        ["Como funciona o limite de taxa?", "Token bucket: enche rpm/60 fichas por segundo até o burst; sem ficha, "
                                            "429", "security.py"],
        ["O que o TLS protege e o que a chave protege?", "TLS: usuário ↔ gateway. Chave: ninguém mais usa o nó",
         "lab.py, node.py"],
        ["Por que o JSON é sempre válido?", "Geração restrita ao JSON Schema e validação de novo com Pydantic",
         "llama_server.py, clinical/schema.py"],
        ["Por que não continuar a resposta em outro nó?", "Com JSON forçado não funciona e não dá para verificar a "
                                                          "emenda", "PLANO.md, D9"],
        ["Onde ficam os dados?", "Em memória; disco só tem log sem texto e hash dos tokens; não há banco",
         "metrics.py"],
    ], [4.6, 8.2, 4.2]))
    h.append(PageBreak())

    # ---- parte 7: fala e checklist
    h.append(P("7. Roteiro de fala (~10 min) e checklist do dia", "h1"))
    h.append(P("Divisão sugerida: cada um apresenta uma parte, <b>mas todos precisam responder sobre todas</b>.",
               "pequeno"))
    h.append(tabela(["Min.", "Quem (sugestão)", "Assunto", "Mostrar"], [
        ["0-1", "Eduardo", "O problema: IA como fila, roteamento e transporte; os 2 domínios", "Diagrama da pág. 4"],
        ["1-4", "Lívia", "Demo ao vivo: tela, posição na fila com 3 abas, prontuário em cartões, métricas",
         "Teste 1 ou 2"],
        ["4-6", "Daniel", "Distribuição: nós em outros PCs, chave de API, balanceamento, queda de um nó",
         "Testes 3 e 4, Wireshark"],
        ["6-8", "Eduardo", "Decisões e trade-offs: TCP/SSE, event loop, K vagas, failover", "Tabela da pág. 5"],
        ["8-10", "Lívia", "Experimento: previsão × medição, pergunta-desafio, o que o ensaio pegou",
         "Gráfico real (teste 5)"],
    ], [1.2, 2.6, 8.7, 4.5]))
    h.append(P("Checklist do dia", "h2"))
    for item in [
        "<b>O mesmo t2-lab.zip</b> no e-mail dos três (um pacote só) e o cache de modelos no pendrive",
        "<font name='Mono'>python3 lab.py chave</font> com a mesma impressão em todos os PCs",
        "Teste 1 rodado no PC da apresentação <b>antes</b> do professor chegar (modelo já carregado)",
        "IPs anotados; <font name='Mono'>curl http://IP:8101/health</font> conferido entre os PCs",
        "Prints de reserva: tela com fila, Wireshark, /metrics, gráficos do experimento",
        "Resultado real do experimento commitado em <font name='Mono'>experiments/resultados/</font> e números no "
        "<font name='Mono'>docs/RELATORIO.md</font>",
        "README do Frontend corrigido (o commit de 11/11 diz que não existe lab.py demo: está desatualizado)",
        "Cada um leu o <font name='Mono'>docs/MUDANCAS.md</font> e a seção de perguntas do "
        "<font name='Mono'>EXPLICACAO.md</font>",
    ]:
        h.append(P(f"<font name='Simbolo'>☐</font>&nbsp;&nbsp;{item}"))
    h.append(Spacer(1, 0.3 * cm))
    h.append(P("Limitações para dizer com honestidade", "h2"))
    h.append(tabela(["Limitação", "Por que é aceitável aqui"], [
        ["Um processo de gateway (filas em memória)", "Escopo do trabalho; Redis/fila externa seria o próximo passo"],
        ["Falha depois do 1º token = erro parcial", "Decisão consciente (pág. 5); o cliente reenvia"],
        ["Só CPU: prontuário com o modelo grande leva ~1 min", "Hardware do lab; GPU é melhoria futura"],
        ["Validar o JSON não garante o conteúdo", "Medimos no teste real; por isso o prontuário usa o modelo grande"],
    ], [7, 10]))
    h.append(PageBreak())
    h += parte_8()
    return h


def parte_8():
    h = [P("8. Solução de problemas na rede local", "h1"),
         P("Para consertar <b>durante a apresentação</b>. Vá na ordem: cada passo elimina uma causa.")]
    h.append(P("Diagnóstico em 4 comandos", "h2"))
    h.append(tabela(["#", "Onde", "Comando", "Resultado certo", "Se der errado"], [
        ["1", "PC do nó", "<font name='Mono'>python3 lab.py no --modelo pequeno</font>",
         "\"nó ... pronto em http://IP:8101\" e o terminal <b>continua aberto</b>",
         "Ctrl+C para o nó. Ler <font name='Mono'>.lab/logs/&lt;nó&gt;.log</font> se ele morreu"],
        ["2", "PC do gateway", "<font name='Mono'>curl http://IP_NO:8101/health</font>",
         "<font name='Mono'>{\"status\":\"ok\"}</font>",
         "\"Couldn't connect\" na hora: nó parado ou IP errado. Demora e dá timeout: firewall ou rede diferente"],
        ["3", "Todos os PCs", "<font name='Mono'>python3 lab.py chave</font>", "Mesmos 12 dígitos em todos",
         "Sobrescrever a chave (abaixo) e reiniciar o nó"],
        ["4", "PC do gateway",
         "<font name='Mono'>python3 lab.py gateway --publico --nos redes=IP_NO:8101</font>",
         "Banner \"T2 no ar\" e a tela respondendo", "Ver a mensagem de erro na tela (tabela abaixo)"],
    ], [0.6, 2.2, 5.3, 4.2, 4.7]))
    h.append(P("Sobrescrever a chave (1 minuto, sem gerar outro pacote)", "h2"))
    h.append(codigo("""
# no PC do gateway (a chave "certa"):
python3 lab.py chave --mostrar
# no PC do nó (a chave errada):
python3 lab.py chave --definir 'COLE_A_CHAVE_AQUI'
# no PC do nó: Ctrl+C no nó e suba de novo (o llama-server só lê a chave ao iniciar)
python3 lab.py no --modelo pequeno
"""))
    h.append(P("Mensagens de erro e correções", "h2"))
    h.append(tabela(["Mensagem / sintoma", "Causa", "Correção"], [
        ["<b>nó ... recusou a chave de API</b>", "Chaves diferentes (zips de pacotes diferentes)",
         "Sobrescrever a chave e reiniciar o nó. <i>Boa notícia: a rede funciona, o 401 veio do nó</i>"],
        ["<b>nenhum nó saudável</b> (503)", "O gateway não alcança nenhum nó; o /health é checado a cada 2 s",
         "Passo 2 (<font name='Mono'>curl</font>) no PC do gateway; esperar 2 s depois do nó subir"],
        ["<b>curl: Couldn't connect</b>", "Nó parado, porta errada, ou IP da rede virtual "
         "<font name='Mono'>192.168.122.x</font>", "Subir o nó e usar o IP que o <font name='Mono'>lab.py no</font> "
         "imprimiu (<font name='Mono'>192.168.112.x</font> ou <font name='Mono'>10.9.12.x</font>)"],
        ["<b>curl</b> fica esperando (timeout)", "Firewall ou PCs em redes diferentes",
         "Tentar o outro IP do <font name='Mono'>hostname -I</font>; se nada passar, plano B"],
        ["<b>Confirme que confia na origem HTTPS</b>", "Tela aberta de outro PC (https://IP_A:8443)",
         "Marcar a caixa \"Confio nesta origem HTTPS\" antes de enviar"],
        ["Navegador: certificado desconhecido", "CA local do trabalho", "Avançado → Continuar"],
        ["<b>401 / token inválido</b> na tela", "Token de outro PC: cada gateway gera o seu",
         "Colar o token impresso pelo gateway que está no ar (<font name='Mono'>.lab/token</font> do PC-A)"],
        ["<b>capacidade esgotada</b> (503 queue_full)", "Fila do nó cheia", "Esperar alguns segundos e reenviar"],
        ["Erro com texto pela metade (partial)", "O nó caiu durante a resposta",
         "Esperado no teste 4 (falha de nó). Reenviar: vai para outra réplica"],
        ["Prontuário demora ~1 min ou dá prazo excedido", "Modelo grande em CPU",
         "Enviar um pedido por vez; não abrir várias abas no prontuário"],
        ["Porta em uso / endereço em uso", "Processo que sobrou de uma execução anterior",
         "Rodar o mesmo comando de novo (ele encerra o que sobrou) ou "
         "<font name='Mono'>pkill -f llama-server</font>"],
        ["Nó morre ao subir (log: memory / failed to load)", "Falta RAM", "<font name='Mono'>--leve</font> ou outro PC"],
        ["Wireshark sem permissão", "Usuário do lab sem sudo",
         "Provar com <font name='Mono'>ss -tn | grep 8101</font> e o log do nó (abaixo)"],
        ["Log do nó sem linhas novas ao enviar", "O pedido foi para outro nó (ou o demo local está rodando)",
         "No PC do gateway, <font name='Mono'>pgrep -a llama-server</font> tem que vir vazio"],
    ], [4.4, 5.2, 7.4]))
    h.append(P("Como provar que o modelo roda no outro PC", "h2"))
    h.append(tabela(["Prova", "Onde", "Comando / ação"], [
        ["O modelo rodou <b>neste</b> PC: a cada pergunta aparecem <font name='Mono'>launch_slot</font>, "
         "<font name='Mono'>print_timing</font> (tokens/s) e <font name='Mono'>release</font>", "PC do nó",
         "<font name='Mono'>tail -f .lab/logs/&lt;nó&gt;.log</font> e enviar uma pergunta pela tela"],
        ["O pedido veio <b>do gateway</b>: conexão TCP com o IP do PC-A (o log não mostra IP)", "PC do nó",
         "<font name='Mono'>ss -tn | grep 8101</font> durante a resposta"],
        ["Conexão TCP aberta para o nó", "PC do gateway", "<font name='Mono'>ss -tn | grep 8101</font> durante a "
                                                          "resposta"],
        ["Nenhum modelo no PC do gateway", "PC do gateway", "<font name='Mono'>pgrep -a llama-server</font> "
                                                            "(não mostra nada)"],
        ["CPU do nó a 100% só durante a geração", "PC do nó", "<font name='Mono'>top</font>"],
        ["Derrubar o nó derruba a resposta", "PC do nó", "Ctrl+C → a tela passa a dar \"nenhum nó saudável\""],
    ], [6.2, 3, 7.8]))
    h.append(P("<b>Plano B se a rede falhar na hora:</b> <font name='Mono'>python3 lab.py demo --leve</font> num PC "
               "só (sobe em ~15 s), mostrar o diagrama da pág. 4 e os <b>prints do teste distribuído</b> tirados "
               "antes. Tirem esses prints no ensaio!", "aviso"))
    return h


def main():
    doc = SimpleDocTemplate(str(SAIDA), pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=1.8 * cm,
                            bottomMargin=1.8 * cm, title="T2 - roteiro de teste e apresentação",
                            author="Daniel, Lívia e Eduardo")
    doc.build(montar(), onFirstPage=rodape, onLaterPages=rodape)
    print(SAIDA)


if __name__ == "__main__":
    main()
