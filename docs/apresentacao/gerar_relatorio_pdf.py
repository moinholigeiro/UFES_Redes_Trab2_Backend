"""Gera docs/RELATORIO.pdf a partir de docs/RELATORIO.md.

Uso (na raiz do Backend):  python docs/apresentacao/gerar_relatorio_pdf.py
Requer: markdown-it-py e Chrome ou Edge instalado (impressão em PDF sem janela).
O diagrama mermaid é desenhado pelo mermaid.js (CDN), então precisa de internet.
"""
import os
import pathlib
import re
import shutil
import subprocess
import tempfile

from markdown_it import MarkdownIt

AQUI = pathlib.Path(__file__).resolve().parent
DOCS = AQUI.parent
ORIGEM = DOCS / "RELATORIO.md"
DESTINO = DOCS / "RELATORIO.pdf"
REPO = "https://github.com/moinholigeiro/UFES_Redes_Trab2_Backend/blob/main/"

CSS = """
@page { size: A4; margin: 16mm 15mm 16mm 15mm; }
body { font-family: Arial, Helvetica, sans-serif; font-size: 10.2pt; line-height: 1.42; color: #1a1a1a; }
h1 { font-size: 19pt; color: #1f4e79; margin: 0 0 4px; }
h2 { font-size: 13.5pt; color: #1f4e79; margin: 18px 0 6px; border-bottom: 1px solid #c9d6e3; padding-bottom: 2px;
     break-after: avoid; }
p { margin: 5px 0; }
ul, ol { margin: 4px 0 6px; padding-left: 20px; }
li { margin: 2px 0; }
table { border-collapse: collapse; width: 100%; margin: 6px 0 10px; font-size: 9.2pt; break-inside: auto; }
tr { break-inside: avoid; }
th { background: #1f4e79; color: #fff; text-align: left; padding: 4px 6px; }
td { border-bottom: 1px solid #dde3ea; padding: 4px 6px; vertical-align: top; }
tr:nth-child(even) td { background: #f4f7fa; }
code { font-family: Consolas, monospace; font-size: 9pt; background: #eef2f6; padding: 0 3px; border-radius: 3px; }
a { color: #1f5fa8; text-decoration: none; }
.mermaid { text-align: center; margin: 8px 0 10px; }
.mermaid svg { max-width: 100%; height: auto; }
"""


def html_do_relatorio() -> str:
    md = ORIGEM.read_text(encoding="utf-8")
    md = re.sub(r"^Versão em PDF:.*\n", "", md, flags=re.M)  # o PDF não aponta para si mesmo
    # links relativos viram links do GitHub, para funcionarem no PDF
    def absoluto(m):
        alvo = m.group(2)
        if re.match(r"https?://|#", alvo):
            return m.group(0)
        caminho = os.path.normpath(os.path.join("docs", alvo)).replace("\\", "/")
        return f"[{m.group(1)}]({REPO}{caminho})"
    md = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", absoluto, md)

    mdi = MarkdownIt("commonmark").enable("table")
    padrao = mdi.renderer.rules.get("fence")

    def fence(self, tokens, idx, options, env):
        t = tokens[idx]
        if t.info.strip() == "mermaid":
            return f'<div class="mermaid">{t.content}</div>'
        return padrao(tokens, idx, options, env)
    mdi.add_render_rule("fence", fence)
    corpo = mdi.render(md)
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<title>Relatório T2 Redes</title><style>{CSS}</style>
<script src="https://cdn.jsdelivr.net/npm/mermaid@10.9.1/dist/mermaid.min.js"></script>
</head><body>{corpo}
<script>mermaid.initialize({{startOnLoad: true, theme: "neutral", flowchart: {{htmlLabels: true}}}});</script>
</body></html>"""


def navegador() -> str:
    for c in [r"C:\Program Files\Google\Chrome\Application\chrome.exe",
              r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
              "google-chrome", "chromium", "chromium-browser"]:
        if os.path.exists(c) or shutil.which(c):
            return c
    raise SystemExit("Chrome/Edge não encontrado")


def main():
    with tempfile.TemporaryDirectory() as tmp:
        html = pathlib.Path(tmp) / "relatorio.html"
        html.write_text(html_do_relatorio(), encoding="utf-8")
        subprocess.run([navegador(), "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                        "--virtual-time-budget=15000", f"--user-data-dir={tmp}/perfil",
                        f"--print-to-pdf={DESTINO}", html.as_uri()],
                       check=True, capture_output=True, timeout=120)
    print(DESTINO)


if __name__ == "__main__":
    main()
