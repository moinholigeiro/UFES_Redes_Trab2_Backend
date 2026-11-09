#!/usr/bin/env python3
"""Lançador do T2 para o laboratório: um comando sobe o sistema inteiro, igual em qualquer máquina.

    python3 lab.py demo                 # cenário 1: tudo nesta máquina (2 modelos, gateway, tela)
    python3 lab.py demo --leve          # idem com um modelo só (~2 GB de RAM)
    python3 lab.py no --modelo pequeno  # cenários 2 a 5: só um nó LLM nesta máquina, aberto na LAN
    python3 lab.py gateway --nos redes=10.0.0.5:8101,prontuario=10.0.0.5:8102
    python3 lab.py experimento          # experimento obrigatório + pergunta-desafio, com gráficos
    python3 lab.py experimento --simulado   # ensaio rápido, sem modelo (não é resultado)
    python3 lab.py baixar --destino /media/pendrive/t2-cache   # binário + modelos para levar
    python3 lab.py pacote               # t2-lab.zip com os 3 repositórios, para o laboratório

O que ele faz sozinho, na primeira vez:
  1. cria o ambiente Python em UFES_Redes_Trab2_Backend/.venv (com o Python da máquina, se for 3.12+;
     senão baixa o `uv`, que traz um Python 3.12 só para esta pasta);
  2. baixa o llama-server oficial (llama.cpp, versão fixa) e os modelos, conferindo o SHA-256;
  3. gera a chave entre gateway e nós, o token de acesso e o certificado TLS do gateway.
Nada é instalado no sistema: apagar a pasta desfaz tudo. Estado e logs ficam em .lab/.

Só precisa de Python 3.8+ para começar. Funciona em Linux (laboratório) e Windows.
Detalhes e solução de problemas: docs/LABORATORIO.md.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import secrets
import shutil
import signal
import socket
import ssl
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parent
RAIZ = BACKEND.parent
LLM = RAIZ / "UFES_Redes_Trab2_LLM"
FRONTEND = RAIZ / "UFES_Redes_Trab2_Frontend"
ESTADO = BACKEND / ".lab"
WINDOWS = os.name == "nt"

# Binário oficial do llama.cpp, fixado por versão e SHA-256 (github.com/ggml-org/llama.cpp/releases).
LLAMA_VERSAO = "b12211"
LLAMA = {
    "linux": (
        f"https://github.com/ggml-org/llama.cpp/releases/download/{LLAMA_VERSAO}/"
        f"llama-{LLAMA_VERSAO}-bin-ubuntu-x64.tar.gz",
        "962924b5431bc1237a9e5d26ba072d37b6fe05f79b495206e7ff6134887624c5",
    ),
    "windows": (
        f"https://github.com/ggml-org/llama.cpp/releases/download/{LLAMA_VERSAO}/"
        f"llama-{LLAMA_VERSAO}-bin-win-cpu-x64.zip",
        "23729000408c6968faf5e322afc99319d3b8c576ba872ef7663d9b89810090f3",
    ),
}
# uv: só é baixado se o Python da máquina for anterior ao 3.12 (github.com/astral-sh/uv/releases).
UV_VERSAO = "0.13.7"
UV = {
    "linux": (
        f"https://github.com/astral-sh/uv/releases/download/{UV_VERSAO}/uv-x86_64-unknown-linux-gnu.tar.gz",
        "c5221ff41b7892bfc223543883600125f6a47fe845093e0f5bdff4f359196d83",
    ),
    "windows": (
        f"https://github.com/astral-sh/uv/releases/download/{UV_VERSAO}/uv-x86_64-pc-windows-msvc.zip",
        "0cdc5b38fe5a8168ed6a25814f5ba43c21d313dd3187314fccb37b7cec46e021",
    ),
}
# Apelido usado na linha de comando -> id do modelo no manifesto do repositório LLM.
MODELOS = {"pequeno": "qwen3-1.7b-q4_k_m", "grande": "qwen3.5-4b-q4_k_m"}
PORTAS = {"pequeno": 8101, "grande": 8102}
PORTA_GATEWAY = 8443

PROCESSOS: list[tuple[str, subprocess.Popen]] = []


# --------------------------------------------------------------------------------------------------
# utilidades


def info(msg: str) -> None:
    print(f"[lab] {msg}", flush=True)


def falha(msg: str) -> None:
    print(f"[lab] ERRO: {msg}", file=sys.stderr, flush=True)
    raise SystemExit(2)


def sistema() -> str:
    if WINDOWS:
        return "windows"
    if sys.platform.startswith("linux") and platform.machine() in ("x86_64", "AMD64"):
        return "linux"
    falha(f"sistema não suportado pelo lab.py: {sys.platform}/{platform.machine()} (use o devenv)")
    return ""


def sha256(caminho: Path) -> str:
    h = hashlib.sha256()
    with caminho.open("rb") as fh:
        for bloco in iter(lambda: fh.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def baixar(url: str, destino: Path, esperado: str, cache: Path | None) -> Path:
    """Baixa (ou copia do cache) e confere o SHA-256. Nunca usa um arquivo que não confere."""
    if destino.is_file() and sha256(destino) == esperado:
        return destino
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporario = destino.with_name(destino.name + ".parcial")
    origem_cache = cache / destino.name if cache else None
    if origem_cache and origem_cache.is_file():
        info(f"copiando {destino.name} do cache {cache}")
        shutil.copyfile(origem_cache, temporario)
    else:
        info(f"baixando {destino.name} ...")
        try:
            with urllib.request.urlopen(url, timeout=60) as resp, temporario.open("wb") as fh:
                total = int(resp.headers.get("Content-Length") or 0)
                lido, ultimo = 0, 0.0
                while True:
                    bloco = resp.read(1 << 20)
                    if not bloco:
                        break
                    fh.write(bloco)
                    lido += len(bloco)
                    if total and time.monotonic() - ultimo > 2:
                        ultimo = time.monotonic()
                        print(f"      {lido / total:6.1%} de {total / 1e6:,.0f} MB", flush=True)
        except (urllib.error.URLError, OSError) as exc:
            temporario.unlink(missing_ok=True)
            falha(f"não consegui baixar {url}: {exc}. Sem internet? Use --cache com o pendrive.")
    obtido = sha256(temporario)
    if obtido != esperado:
        temporario.unlink()
        falha(f"SHA-256 de {destino.name} não confere (esperado {esperado[:12]}…, obtido {obtido[:12]}…)")
    os.replace(temporario, destino)
    return destino


def manifesto() -> dict[str, dict]:
    caminho = LLM / "models" / "manifest.json"
    if not caminho.is_file():
        falha(f"repositório LLM não encontrado em {LLM}. Os 3 repositórios precisam estar lado a lado.")
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    return {m["id"]: m for m in dados["models"]}


def ip_da_lan() -> str:
    """IP desta máquina na rede local (não envia nenhum pacote)."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
        except OSError:
            return "127.0.0.1"


def esperar_http(url: str, *, ca: Path | None = None, limite_s: float = 600, rotulo: str = "") -> None:
    """Espera um GET devolver 200 (o modelo leva de segundos a minutos para carregar)."""
    contexto = ssl.create_default_context(cafile=str(ca)) if ca else None
    inicio = time.monotonic()
    while time.monotonic() - inicio < limite_s:
        for nome, proc in PROCESSOS:
            if proc.poll() is not None:
                falha(f"{nome} terminou com código {proc.returncode}; veja .lab/logs/{nome}.log")
        try:
            with urllib.request.urlopen(url, timeout=3, context=contexto) as resp:
                if resp.status == 200:
                    return
        except (urllib.error.URLError, OSError, ssl.SSLError):
            pass
        time.sleep(1)
    falha(f"{rotulo or url} não respondeu em {limite_s:.0f} s")


def iniciar(nome: str, comando: list[str], *, env: dict[str, str] | None = None) -> subprocess.Popen:
    (ESTADO / "logs").mkdir(parents=True, exist_ok=True)
    log = (ESTADO / "logs" / f"{nome}.log").open("w", encoding="utf-8")
    if WINDOWS:
        extras = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    else:
        extras = {"start_new_session": True}
    proc = subprocess.Popen(comando, cwd=BACKEND, stdout=log, stderr=subprocess.STDOUT,
                            env={**os.environ, **(env or {})}, **extras)
    PROCESSOS.append((nome, proc))
    info(f"{nome} iniciado (pid {proc.pid}); log em .lab/logs/{nome}.log")
    return proc


def parar_tudo() -> None:
    while PROCESSOS:
        nome, proc = PROCESSOS.pop()
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                proc.kill()
            info(f"{nome} parado")


def aguardar_ctrl_c() -> None:
    try:
        while True:
            for nome, proc in PROCESSOS:
                if proc.poll() is not None:
                    falha(f"{nome} parou sozinho (código {proc.returncode}); veja .lab/logs/{nome}.log")
            time.sleep(2)
    except KeyboardInterrupt:
        print()
        info("encerrando ...")


# --------------------------------------------------------------------------------------------------
# preparação: Python, binário, modelos, segredos


def venv_bin(nome: str) -> Path:
    pasta = BACKEND / ".venv" / ("Scripts" if WINDOWS else "bin")
    return pasta / (nome + (".exe" if WINDOWS else ""))


def garantir_python(cache: Path | None) -> Path:
    python = venv_bin("python")
    pronto = ESTADO / "venv-pronto"
    if python.is_file() and pronto.is_file():
        return python
    ESTADO.mkdir(parents=True, exist_ok=True)
    pacote = f"{BACKEND}[experiments]"
    if sys.version_info >= (3, 12):
        info("criando o ambiente Python em .venv ...")
        subprocess.check_call([sys.executable, "-m", "venv", str(BACKEND / ".venv")])
        subprocess.check_call([str(python), "-m", "pip", "install", "--quiet", "--upgrade", "pip"])
        subprocess.check_call([str(python), "-m", "pip", "install", "--quiet", "-e", pacote])
    else:
        info(f"Python {platform.python_version()} é anterior ao 3.12: usando o uv para trazer o 3.12")
        url, esperado = UV[sistema()]
        arquivo = baixar(url, ESTADO / "downloads" / url.rsplit("/", 1)[1], esperado, cache)
        destino = ESTADO / "uv"
        extrair(arquivo, destino)
        uv = next(p for p in destino.rglob("uv.exe" if WINDOWS else "uv") if p.is_file())
        uv.chmod(0o755)
        subprocess.check_call([str(uv), "venv", "--python", "3.12", str(BACKEND / ".venv")])
        subprocess.check_call([str(uv), "pip", "install", "--python", str(python), "-e", pacote])
    pronto.write_text(time.strftime("%Y-%m-%d %H:%M:%S"), encoding="utf-8")
    return python


def extrair(arquivo: Path, destino: Path) -> None:
    destino.mkdir(parents=True, exist_ok=True)
    if arquivo.name.endswith(".zip"):
        with zipfile.ZipFile(arquivo) as z:
            z.extractall(destino)
    else:
        with tarfile.open(arquivo) as t:
            if sys.version_info >= (3, 12):
                t.extractall(destino, filter="data")
            else:
                t.extractall(destino)  # arquivo oficial, conferido por SHA-256


def garantir_llama(cache: Path | None) -> Path:
    url, esperado = LLAMA[sistema()]
    pasta = LLM / "bin" / f"llama-{LLAMA_VERSAO}"
    nome = "llama-server.exe" if WINDOWS else "llama-server"
    achados = [p for p in pasta.rglob(nome) if p.is_file()] if pasta.is_dir() else []
    if not achados:
        arquivo = baixar(url, LLM / "bin" / url.rsplit("/", 1)[1], esperado, cache)
        extrair(arquivo, pasta)
        achados = [p for p in pasta.rglob(nome) if p.is_file()]
        if not achados:
            falha(f"{nome} não encontrado dentro de {arquivo.name}")
    binario = achados[0]
    if not WINDOWS:
        binario.chmod(0o755)
    return binario


def garantir_modelo(apelido: str, cache: Path | None) -> tuple[Path, str]:
    modelo = manifesto()[MODELOS[apelido]]
    url = f"{modelo['source']}/resolve/{modelo['revision']}/{modelo['file']}"
    caminho = baixar(url, LLM / "models" / modelo["file"], modelo["sha256"], cache)
    return caminho, modelo["sha256"]


def garantir_chave() -> Path:
    """Chave entre gateway e nós. Precisa ser a MESMA em todas as máquinas (vem no pacote)."""
    chave = ESTADO / "node-api-key"
    if not chave.is_file():
        ESTADO.mkdir(parents=True, exist_ok=True)
        chave.write_text(secrets.token_urlsafe(32), encoding="utf-8")
        if not WINDOWS:
            chave.chmod(0o600)
    return chave


def garantir_token(python: Path) -> str:
    token = ESTADO / "token"
    if token.is_file():
        return token.read_text(encoding="utf-8").strip()
    usuarios = ESTADO / "users.toml"
    usuarios.unlink(missing_ok=True)  # recria junto com o token
    saida = subprocess.check_output(
        [str(python), "-m", "llm_gateway.cli", "token-create", "--users-file", str(usuarios),
         "--username", "lab", "--domains", "redes,prontuario", "--requests-per-minute", "600",
         "--burst", "60", "--metrics"],
        cwd=BACKEND, text=True,
    )
    valor = saida.splitlines()[1].strip()
    token.write_text(valor, encoding="utf-8")
    if not WINDOWS:
        token.chmod(0o600)
    return valor


def garantir_tls(extra_ip: str | None) -> Path | None:
    """Certificado do gateway assinado por uma CA local. Sem openssl, devolve None (HTTP em loopback)."""
    pasta = ESTADO / "tls"
    if (pasta / "gateway.crt").is_file():
        return pasta
    bash = shutil.which("bash")
    if WINDOWS:
        git_bash = Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "Git" / "bin" / "bash.exe"
        bash = str(git_bash) if git_bash.is_file() else None
    tem_openssl = WINDOWS or shutil.which("openssl") is not None  # o Git for Windows traz o openssl
    if not bash or not tem_openssl:
        info("openssl/bash não encontrados: o gateway fica em HTTP, só em 127.0.0.1")
        return None
    sans = f"IP:{extra_ip}" if extra_ip and extra_ip != "127.0.0.1" else ""
    subprocess.check_call([bash, str(BACKEND / "scripts" / "generate-local-ca.sh"), str(pasta), sans],
                          cwd=BACKEND)
    return pasta


# --------------------------------------------------------------------------------------------------
# configurações geradas


def toml_path(p: Path) -> str:
    return json.dumps(p.resolve().as_posix())


MODELOS_TOML = """
[models."qwen3-1.7b"]
family = "qwen3"
quantization = "Q4_K_M"
source = "unsloth/Qwen3-1.7B-GGUF@d7f544eead698dbd1f15126ef60b45a1e1933222"
license = "apache-2.0 (Qwen/Qwen3-1.7B)"
sha256 = "b139949c5bd74937ad8ed8c8cf3d9ffb1e99c866c823204dc42c0d91fa181897"
context_tokens = 4096

[models.qwen35-4b]
family = "qwen3.5"
quantization = "Q4_K_M"
source = "unsloth/Qwen3.5-4B-GGUF@e87f176479d0855a907a41277aca2f8ee7a09523"
license = "apache-2.0 (Qwen/Qwen3.5-4B)"
sha256 = "00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4"
context_tokens = 4096
"""

MODELO_TOML = {"pequeno": "qwen3-1.7b", "grande": "qwen35-4b"}


def config_no(nome: str, apelido: str, caminho_modelo: Path, sha: str, *, porta: int, slots: int,
              threads: int, publico: bool) -> Path:
    bind = "0.0.0.0" if publico else "127.0.0.1"
    url_publica = f"http://{ip_da_lan() if publico else '127.0.0.1'}:{porta}"
    texto = "\n".join([
        f"# Gerado pelo lab.py em {time.strftime('%Y-%m-%d %H:%M')}. Não edite: rode o lab.py de novo.",
        f'node_id = "{nome}"',
        f'bind_host = "{bind}"',
        f"bind_port = {porta}",
        f'public_url = "{url_publica}"',
        f"model_file = {toml_path(caminho_modelo)}",
        f'model_sha256 = "{sha}"',
        f"threads = {threads}",
        "context_tokens = 4096",
        f"slots = {slots}",
        "n_gpu_layers = 0",
        f"api_key_file = {toml_path(garantir_chave())}",
        "chat_template_kwargs = { enable_thinking = false }",
        "",
    ])
    destino = ESTADO / "nos" / f"{nome}.toml"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(texto, encoding="utf-8")
    return destino


def config_gateway(nos: list[tuple[str, str, str]], *, leve: bool, tls: Path | None, publico: bool,
                   k: int, politica_fila: str, balanceamento: str, experimento: bool,
                   simulado: bool = False) -> Path:
    """nos: (nome, apelido do modelo, url). Gera .lab/gateway.toml."""
    host = "0.0.0.0" if publico else "127.0.0.1"
    linhas = [
        f"# Gerado pelo lab.py em {time.strftime('%Y-%m-%d %H:%M')}. Não edite: rode o lab.py de novo.",
        "[gateway]",
        f'host = "{host}"',
        f"port = {PORTA_GATEWAY}",
        "max_input_chars = 8000",
        "max_output_tokens_limit = 1024",
        f"request_deadline_s = {1200.0 if experimento else 600.0}",
        f"queue_timeout_s = {900.0 if experimento else 120.0}",
        "client_stall_timeout_s = 60.0",
        "backend_read_timeout_s = 120.0",
        "heartbeat_interval_s = 10.0",
        f"metrics_log = {toml_path(ESTADO / 'logs' / 'requests.jsonl')}",
        f"frontend_dir = {toml_path(FRONTEND)}" if (FRONTEND / "index.html").is_file() else "",
        f"allow_simulated_backends = {'true' if simulado else 'false'}",
    ]
    if tls:
        linhas += [f"tls_certfile = {toml_path(tls / 'gateway.crt')}",
                   f"tls_keyfile = {toml_path(tls / 'gateway.key')}"]
    linhas += [
        "",
        "[security]",
        "enabled = true",
        f"users_file = {toml_path(ESTADO / 'users.toml')}",
        f"require_tls = {'true' if tls else 'false'}",
        "",
        "[scheduling]",
        f'policy = "{politica_fila}"',
        "aging_s = 30.0",
        "",
        "[balancing]",
        f'policy = "{balanceamento}"',
    ]
    if simulado:
        linhas += ['', '[models.sim-small]', 'family = "simulado"', 'quantization = "none"',
                   'source = "backend simulado"', 'license = "n/a"']
        redes_modelo, pront_modelo = "sim-small", None
    else:
        linhas.append(MODELOS_TOML)
        redes_modelo = "qwen3-1.7b"
        pront_modelo = "qwen3-1.7b" if leve else "qwen35-4b"
    linhas += [
        "",
        "[domains.redes]",
        'description = "Assistente da disciplina de Redes de Computadores"',
        f'models = ["{redes_modelo}"]',
        'prompt = "redes-v1"',
        'output = "text"',
        f"temperature = {0.0 if experimento else 0.7}",
        "top_p = 0.8",
        "top_k = 20",
        "default_max_output_tokens = 512",
        "max_output_tokens = 1024",
    ]
    if pront_modelo:
        linhas += [
            "",
            "[domains.prontuario]",
            'description = "Extração estruturada de prontuário sintético (não é ferramenta clínica)"',
            f'models = ["{pront_modelo}"]',
            'prompt = "prontuario-v1"',
            'output = "json_extraction"',
            'schema = "prontuario-v1"',
            "temperature = 0.0",
            "top_p = 1.0",
            "top_k = 0",
            "default_max_output_tokens = 768",
            "max_output_tokens = 1024",
        ]
    for nome, apelido, url in nos:
        linhas += ["", "[[nodes]]", f'name = "{nome}"']
        if simulado:
            linhas += [
                'kind = "simulated"', 'model = "sim-small"', f"max_inflight = {k}", "max_queue = 64",
                "[nodes.simulation]", "tokens_per_second = 40.0", "startup_delay_s = 0.2",
                "report_usage = true",
                'response = "' + ("A camada de transporte oferece comunicação lógica entre processos. " * 80)
                + '"',
            ]
        else:
            linhas += [
                f'url = "{url}"', f'model = "{MODELO_TOML[apelido]}"', f"max_inflight = {k}",
                "max_queue = 64", f"api_key_file = {toml_path(garantir_chave())}",
                "chat_template_kwargs = { enable_thinking = false }",
            ]
    destino = ESTADO / "gateway.toml"
    destino.write_text("\n".join(x for x in linhas if x is not None) + "\n", encoding="utf-8")
    return destino


# --------------------------------------------------------------------------------------------------
# subir as peças


def subir_no(python: Path, apelido: str, *, nome: str, porta: int, slots: int, threads: int,
             publico: bool, cache: Path | None) -> str:
    binario = garantir_llama(cache)
    caminho, sha = garantir_modelo(apelido, cache)
    config = config_no(nome, apelido, caminho, sha, porta=porta, slots=slots, threads=threads,
                       publico=publico)
    iniciar(nome, [str(python), str(LLM / "scripts" / "node.py"), "--config", str(config),
                   "--bin", str(binario)])
    info(f"carregando o modelo {apelido} em {nome} (pode levar um minuto) ...")
    esperar_http(f"http://127.0.0.1:{porta}/health", limite_s=900, rotulo=nome)
    return f"http://{ip_da_lan() if publico else '127.0.0.1'}:{porta}"


def subir_gateway(python: Path, config: Path, tls: Path | None) -> str:
    gateway = venv_bin("llm-gateway")
    iniciar("gateway", [str(gateway), "serve", "--config", str(config)])
    esquema = "https" if tls else "http"
    url_local = f"{esquema}://127.0.0.1:{PORTA_GATEWAY}"
    esperar_http(f"{url_local}/health", ca=(tls / "ca.crt") if tls else None, limite_s=120, rotulo="gateway")
    return url_local


def threads_padrao(quantos_nos: int) -> int:
    return max(1, (os.cpu_count() or 4) // max(1, quantos_nos))


def banner(url: str, token: str, tls: Path | None, publico: bool) -> None:
    linha = "=" * 78
    print(f"\n{linha}")
    print(f"  T2 no ar.  Tela e API:  {url}")
    if publico:
        print(f"  Na rede do laboratório:  {url.replace('127.0.0.1', ip_da_lan())}")
    print(f"  Token (cole na tela):    {token}")
    if tls:
        print(f"  Certificado da CA:       {tls / 'ca.crt'}")
        print("  O navegador vai avisar que o certificado é desconhecido: é a CA local deste trabalho.")
        print("  Clique em 'Avançado' e continue, ou importe o ca.crt no navegador.")
    print(f"  Métricas:  curl -H 'Authorization: Bearer <token>' {url}/metrics")
    print("  Ctrl+C encerra tudo.")
    print(f"{linha}\n", flush=True)


# --------------------------------------------------------------------------------------------------
# comandos


def cmd_demo(args: argparse.Namespace) -> int:
    cache = args.cache or (RAIZ / "cache" if (RAIZ / "cache").is_dir() else None)
    python = garantir_python(cache)
    token = garantir_token(python)
    tls = garantir_tls(None)
    apelidos = ["pequeno"] if args.leve else ["pequeno", "grande"]
    threads = args.threads or threads_padrao(len(apelidos))
    nos = []
    for apelido in apelidos:
        nome = "redes-1" if apelido == "pequeno" else "prontuario-1"
        url = subir_no(python, apelido, nome=nome, porta=PORTAS[apelido], slots=1, threads=threads,
                       publico=False, cache=cache)
        nos.append((nome, apelido, url))
    config = config_gateway(nos, leve=args.leve, tls=tls, publico=False, k=1, politica_fila="fifo",
                            balanceamento="round_robin", experimento=False)
    url = subir_gateway(python, config, tls)
    banner(url, token, tls, publico=False)
    aguardar_ctrl_c()
    return 0


def cmd_no(args: argparse.Namespace) -> int:
    cache = args.cache or (RAIZ / "cache" if (RAIZ / "cache").is_dir() else None)
    python = garantir_python(cache)
    porta = args.porta or PORTAS[args.modelo]
    nome = args.nome or f"{'redes' if args.modelo == 'pequeno' else 'prontuario'}-{socket.gethostname()}"
    url = subir_no(python, args.modelo, nome=nome, porta=porta, slots=args.slots,
                   threads=args.threads or threads_padrao(1), publico=True, cache=cache)
    print(f"\n[lab] nó {nome} pronto em {url}  (modelo {args.modelo}, {args.slots} vaga(s)).")
    print(f"[lab] No gateway, use:  --nos {'redes' if args.modelo == 'pequeno' else 'prontuario'}"
          f"={url.split('//')[1]}")
    print("[lab] A chave entre gateway e nó é .lab/node-api-key: precisa ser a mesma nas duas máquinas.\n")
    aguardar_ctrl_c()
    return 0


def parse_nos(texto: str) -> list[tuple[str, str, str]]:
    nos = []
    for i, item in enumerate(texto.split(","), start=1):
        dominio, _, endereco = item.partition("=")
        if dominio not in ("redes", "prontuario") or ":" not in endereco:
            falha(f"--nos: use dominio=ip:porta, ex.: redes=10.0.0.5:8101 (recebido {item!r})")
        apelido = "pequeno" if dominio == "redes" else "grande"
        nos.append((f"{dominio}-{i}", apelido, f"http://{endereco}"))
    return nos


def cmd_gateway(args: argparse.Namespace) -> int:
    python = garantir_python(args.cache)
    token = garantir_token(python)
    tls = garantir_tls(ip_da_lan() if args.publico else None)
    if args.publico and not tls:
        falha("gateway aberto na rede exige TLS, e o openssl não foi encontrado")
    nos = parse_nos(args.nos)
    leve = not any(apelido == "grande" for _, apelido, _ in nos)
    config = config_gateway(nos, leve=leve, tls=tls, publico=args.publico, k=args.k,
                            politica_fila=args.politica_fila, balanceamento=args.balanceamento,
                            experimento=args.experimento)
    url = subir_gateway(python, config, tls)
    banner(url, token, tls, publico=args.publico)
    aguardar_ctrl_c()
    return 0


def rodar_carga(python: Path, url: str, token_file: Path, ca: Path | None, *, clientes: int, pedidos: int,
                max_tokens: int, saida: Path, rotulos: dict[str, object], fracao_curtos: float = 0.0,
                aquecimento: bool = True) -> None:
    comando = [str(python), str(BACKEND / "experiments" / "carga.py"), "--url", url,
               "--token-file", str(token_file), "--clientes", str(clientes), "--pedidos", str(pedidos),
               "--max-tokens", str(max_tokens), "--saida", str(saida),
               "--fracao-curtos", str(fracao_curtos)]
    if ca:
        comando += ["--ca", str(ca)]
    if not aquecimento:
        comando.append("--sem-aquecimento")
    for chave, valor in rotulos.items():
        comando += ["--rotulo", f"{chave}={valor}"]
    info(f"carga: N={clientes} {rotulos} -> {saida.name}")
    subprocess.check_call(comando, cwd=BACKEND)


def cmd_experimento(args: argparse.Namespace) -> int:
    cache = args.cache or (RAIZ / "cache" if (RAIZ / "cache").is_dir() else None)
    python = garantir_python(cache)
    garantir_token(python)
    token_file = ESTADO / "token"
    saida = args.saida or (BACKEND / "experiments" / "resultados"
                           / (time.strftime("%Y-%m-%d_%H%M") + ("_simulado" if args.simulado else "")))
    saida.mkdir(parents=True, exist_ok=True)
    clientes = [int(x) for x in args.clientes.split(",")]
    ks = [int(x) for x in args.k.split(",")]
    remoto = args.url is not None
    tls = None if args.simulado or remoto else garantir_tls(None)
    ca = args.ca if remoto else ((tls / "ca.crt") if tls else None)
    (saida / "LEIA-ME.txt").write_text(
        ("ENSAIO SIMULADO: backend sem modelo. Serve para testar as ferramentas; NÃO é resultado.\n"
         if args.simulado else "Medição real.\n")
        + f"Gerado em {time.strftime('%Y-%m-%d %H:%M')} por: python3 lab.py experimento "
        + " ".join(sys.argv[2:]) + "\n", encoding="utf-8")

    def com_pilha(k: int, politica: str):
        """Sobe nós e gateway para (K, política), quando o lab.py controla a pilha."""
        if remoto:
            return args.url.rstrip("/")
        nos = [("redes-1", "pequeno", "")]
        if not args.simulado:
            nos = [("redes-1", "pequeno", subir_no(python, "pequeno", nome="redes-1", porta=PORTAS["pequeno"],
                                                   slots=k, threads=args.threads or threads_padrao(1),
                                                   publico=False, cache=cache))]
        config = config_gateway(nos, leve=True, tls=tls, publico=False, k=k, politica_fila=politica,
                                balanceamento="round_robin", experimento=True, simulado=args.simulado)
        return subir_gateway(python, config, tls)

    try:
        for k in ks:
            url = com_pilha(k, "fifo")
            calibracao = saida / f"calibracao-k{k}.csv"
            rodar_carga(python, url, token_file, ca, clientes=k, pedidos=args.calibracao,
                        max_tokens=args.max_tokens,
                        saida=calibracao, rotulos={"k": k, "politica": "fifo", "rep": 0})
            subprocess.check_call([str(python), str(BACKEND / "experiments" / "previsao.py"), "--calibracao",
                                   str(calibracao), "--k", str(k), "--clientes", args.clientes,
                                   "--saida", str(saida / f"previsao-k{k}.json")], cwd=BACKEND)
            info(f"previsão gravada em {saida / f'previsao-k{k}.json'} ANTES das medições")
            for n in clientes:
                for rep in range(1, args.reps + 1):
                    rodar_carga(python, url, token_file, ca, clientes=n, pedidos=args.pedidos,
                                max_tokens=args.max_tokens, saida=saida / f"k{k}-fifo-n{n}-r{rep}.csv",
                                rotulos={"k": k, "politica": "fifo", "rep": rep}, aquecimento=(rep == 1))
            parar_tudo()
        if args.desafio:
            for politica in ("fifo", "short_first"):
                url = com_pilha(1, politica)
                for rep in range(1, args.reps + 1):
                    rodar_carga(python, url, token_file, ca, clientes=args.desafio_clientes,
                                pedidos=args.pedidos, max_tokens=args.max_tokens_longo,
                                saida=saida / f"desafio-{politica}-r{rep}.csv",
                                rotulos={"k": "1-desafio", "politica": politica, "rep": rep},
                                fracao_curtos=0.5, aquecimento=(rep == 1))
                parar_tudo()
    finally:
        parar_tudo()
    graficos = BACKEND / "experiments" / "graficos.py"
    subprocess.check_call([str(python), str(graficos), "--resultados", str(saida)],
                          cwd=BACKEND)
    info(f"pronto: {saida}")
    return 0


def cmd_baixar(args: argparse.Namespace) -> int:
    destino = args.destino
    destino.mkdir(parents=True, exist_ok=True)
    sistemas = ["linux", "windows"] if args.sistema == "todos" else [args.sistema]
    for nome in sistemas:
        url, esperado = LLAMA[nome]
        baixar(url, destino / url.rsplit("/", 1)[1], esperado, None)
        url, esperado = UV[nome]
        baixar(url, destino / url.rsplit("/", 1)[1], esperado, None)
    for apelido in args.modelos.split(","):
        modelo = manifesto()[MODELOS[apelido]]
        url = f"{modelo['source']}/resolve/{modelo['revision']}/{modelo['file']}"
        baixar(url, destino / modelo["file"], modelo["sha256"], None)
    info(f"cache pronto em {destino}. No laboratório: python3 lab.py demo --cache {destino}")
    return 0


def cmd_pacote(args: argparse.Namespace) -> int:
    """Zip com os 3 repositórios no commit atual + chave compartilhada. Sem credencial no laboratório."""
    if not shutil.which("git"):
        falha("o pacote usa o git para exportar exatamente o que está commitado")
    destino = args.saida or (RAIZ / "t2-lab.zip")
    commits = {}
    with tempfile.TemporaryDirectory() as tmp, zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as zout:
        for repo in (BACKEND, LLM, FRONTEND):
            if not (repo / ".git").exists():
                falha(f"repositório ausente: {repo}")
            sujo = subprocess.check_output(["git", "status", "--porcelain"], cwd=repo, text=True).strip()
            if sujo:
                info(f"aviso: {repo.name} tem mudanças não commitadas; o pacote leva só o commit atual")
            commits[repo.name] = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=repo, text=True
            ).strip()
            arquivo = Path(tmp) / f"{repo.name}.zip"
            subprocess.check_call(["git", "archive", "--format=zip", f"--prefix=t2-lab/{repo.name}/",
                                   "-o", str(arquivo), "HEAD"], cwd=repo)
            with zipfile.ZipFile(arquivo) as zin:
                for item in zin.infolist():
                    zout.writestr(item, zin.read(item.filename))
        zout.writestr(f"t2-lab/{BACKEND.name}/.lab/node-api-key", secrets.token_urlsafe(32))
        if args.cache:
            for arquivo in sorted(Path(args.cache).iterdir()):
                if arquivo.is_file():
                    info(f"incluindo {arquivo.name} ({arquivo.stat().st_size / 1e6:,.0f} MB)")
                    zout.write(arquivo, f"t2-lab/cache/{arquivo.name}")
        leia = [
            "T2 — pacote para o laboratório",
            f"Gerado em {time.strftime('%Y-%m-%d %H:%M')}. Commits:",
            *[f"  {nome}: {sha}" for nome, sha in commits.items()],
            "",
            "Uso:  cd t2-lab/UFES_Redes_Trab2_Backend && python3 lab.py demo",
            "A chave .lab/node-api-key é igual em todas as máquinas que usarem este pacote.",
            "Passo a passo: UFES_Redes_Trab2_Backend/docs/LABORATORIO.md",
        ]
        zout.writestr("t2-lab/LEIA-ME.txt", "\n".join(leia) + "\n")
    info(f"pacote criado: {destino} ({destino.stat().st_size / 1e6:,.1f} MB)")
    return 0


def _sigterm(*_: object) -> None:
    raise KeyboardInterrupt  # `kill` no lab.py encerra os filhos como o Ctrl+C


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="lab.py", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="comando", required=True)

    d = sub.add_parser("demo", help="cenário 1: tudo nesta máquina")
    d.add_argument("--leve", action="store_true", help="um modelo só (o pequeno atende os dois domínios)")
    d.add_argument("--threads", type=int, help="threads por nó (padrão: núcleos ÷ nós)")
    d.add_argument("--cache", type=Path, help="pasta com binário e modelos já baixados (pendrive)")
    d.set_defaults(func=cmd_demo)

    n = sub.add_parser("no", help="só um nó LLM nesta máquina, aberto na rede do laboratório")
    n.add_argument("--modelo", choices=["pequeno", "grande"], default="pequeno")
    n.add_argument("--porta", type=int)
    n.add_argument("--slots", type=int, default=1, help="vagas K do nó (use o mesmo K no gateway)")
    n.add_argument("--threads", type=int, help="menos threads = nó mais lento (cenário 4)")
    n.add_argument("--nome")
    n.add_argument("--cache", type=Path)
    n.set_defaults(func=cmd_no)

    g = sub.add_parser("gateway", help="só o gateway (+ tela), usando nós de outras máquinas")
    g.add_argument("--nos", required=True, help="ex.: redes=10.0.0.5:8101,redes=10.0.0.6:8101")
    g.add_argument("--publico", action="store_true", help="abre o gateway na LAN (exige TLS)")
    g.add_argument("--k", type=int, default=1, help="vagas por nó (igual ao --slots dos nós)")
    g.add_argument("--politica-fila", choices=["fifo", "short_first"], default="fifo")
    g.add_argument("--balanceamento", choices=["round_robin", "least_loaded", "least_latency"],
                   default="round_robin")
    g.add_argument("--experimento", action="store_true", help="timeouts longos e temperatura 0")
    g.add_argument("--cache", type=Path)
    g.set_defaults(func=cmd_gateway)

    e = sub.add_parser("experimento", help="experimento obrigatório e pergunta-desafio")
    e.add_argument("--simulado", action="store_true", help="ensaio sem modelo; NÃO é resultado")
    e.add_argument("--url", help="gateway já no ar em outra máquina (o K vira só rótulo)")
    e.add_argument("--ca", type=Path, help="CA do gateway remoto")
    e.add_argument("--k", default="1,2", help="vagas por nó a medir, ex.: 1,2")
    e.add_argument("--clientes", default="1,2,4,8,16")
    e.add_argument("--reps", type=int, default=5)
    e.add_argument("--pedidos", type=int, default=30, help="pedidos concluídos por execução")
    e.add_argument("--calibracao", type=int, default=10, help="pedidos da calibração (N = K)")
    e.add_argument("--max-tokens", type=int, default=128)
    e.add_argument("--desafio", action="store_true", help="roda também FIFO x curtos primeiro")
    e.add_argument("--desafio-clientes", type=int, default=8)
    e.add_argument("--max-tokens-longo", type=int, default=256)
    e.add_argument("--threads", type=int)
    e.add_argument("--saida", type=Path)
    e.add_argument("--cache", type=Path)
    e.set_defaults(func=cmd_experimento)

    b = sub.add_parser("baixar", help="baixa binários e modelos para um cache (pendrive)")
    b.add_argument("--destino", type=Path, required=True)
    b.add_argument("--sistema", choices=["linux", "windows", "todos"], default="linux")
    b.add_argument("--modelos", default="pequeno,grande")
    b.set_defaults(func=cmd_baixar)

    k = sub.add_parser("pacote", help="zip com os 3 repositórios para o laboratório")
    k.add_argument("--saida", type=Path)
    k.add_argument("--cache", type=Path, help="inclui binários e modelos do cache no zip (fica grande)")
    k.set_defaults(func=cmd_pacote)

    args = p.parse_args(argv)
    if not WINDOWS:
        signal.signal(signal.SIGTERM, _sigterm)
    try:
        return int(args.func(args))
    finally:
        parar_tudo()


if __name__ == "__main__":
    raise SystemExit(main())
