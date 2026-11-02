"""Linha de comando: serve (gateway), runtime (um nó llama-server), check-config."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path
from urllib.parse import urlparse

from .api import CONFIG_ENV
from .config import AppConfig, NodeConfig, load_config
from .routing import SemanticRouter
from .security import load_credentials, new_token, write_credential_file


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    config = load_config(args.config)
    tls_cert = config.gateway.tls_certfile
    tls_key = config.gateway.tls_keyfile
    if config.security.require_tls and (
        tls_cert is None or tls_key is None or not tls_cert.is_file() or not tls_key.is_file()
    ):
        print("TLS obrigatório, mas certificado/chave não encontrados", file=sys.stderr)
        return 2
    os.environ[CONFIG_ENV] = str(Path(args.config).resolve())
    uvicorn.run(
        "llm_gateway.api:create_app_from_env",
        factory=True,
        host=args.host or config.gateway.host,
        port=args.port or config.gateway.port,
        workers=1,
        ssl_certfile=str(tls_cert) if tls_cert else None,
        ssl_keyfile=str(tls_key) if tls_key else None,
        log_level="info",
    )
    return 0


def _runtime_argv(node: NodeConfig, model_file: Path, host: str, port: int) -> list[str]:
    argv = [
        "llama-server",
        "-m",
        str(model_file),
        "--host",
        host,
        "--port",
        str(port),
        "-t",
        str(node.threads),
        "-c",
        str(node.ctx_size),
        # Paralelismo do runtime igual ao limite do gateway: sem fila oculta no llama-server.
        "-np",
        str(node.max_inflight),
        "--jinja",
    ]
    if node.chat_template_kwargs:
        argv += ["--chat-template-kwargs", json.dumps(node.chat_template_kwargs)]
    if node.tls_certfile is not None and node.tls_keyfile is not None:
        argv += ["--ssl-cert-file", str(node.tls_certfile), "--ssl-key-file", str(node.tls_keyfile)]
    return argv


def _cmd_runtime(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    node = next((n for n in config.nodes if n.name == args.node), None)
    if node is None or node.kind != "llama_server":
        print(f"nó llama_server não encontrado: {args.node!r}", file=sys.stderr)
        return 2
    model = config.models[node.model]
    if not model.file.exists():
        print(f"arquivo do modelo ausente: {model.file}", file=sys.stderr)
        return 2
    for path in (node.tls_certfile, node.tls_keyfile):
        if path is not None and not path.is_file():
            print(f"arquivo TLS do nó ausente: {path}", file=sys.stderr)
            return 2
    if shutil.which("llama-server") is None:
        print("llama-server não encontrado; entre no ambiente com `devenv shell`", file=sys.stderr)
        return 2
    parsed = urlparse(node.url or "")
    host, port = parsed.hostname or "127.0.0.1", parsed.port or 8080
    argv = _runtime_argv(node, model.file, host, port)
    print("exec:", " ".join(argv), flush=True)
    os.execvp(argv[0], argv)
    return 0


def _cmd_check(args: argparse.Namespace) -> int:
    config: AppConfig = load_config(args.config)
    ok = True
    for name, model in config.models.items():
        exists = model.file.exists()
        line = f"modelo {name}: {model.file} {'OK' if exists else 'AUSENTE'}"
        if exists and args.verify_models and model.sha256:
            matches = _sha256(model.file) == model.sha256
            line += " sha256 OK" if matches else " sha256 DIVERGENTE"
            ok = ok and matches
        elif exists and args.verify_models and not model.sha256:
            line += " sem sha256 registrado"
        ok = ok and exists
        print(line)
    for dname, dom in config.domains.items():
        nodes = [n.name for n in config.nodes if n.model in dom.models]
        print(f"domínio {dname}: modelos={dom.models} prompt={dom.prompt} nós={nodes}")
    if config.security.enabled:
        credential_path = config.security.users_file
        if credential_path is None or not credential_path.is_file():
            print(f"credenciais ausentes: {credential_path}")
            ok = False
        else:
            try:
                credentials = load_credentials(credential_path, set(config.domains))
                print(f"credenciais: {len(credentials.users)} usuário(s), hashes válidos")
            except ValueError as exc:
                print(f"credenciais inválidas: {exc}")
                ok = False
    for label, path in (
        ("certificado TLS", config.gateway.tls_certfile),
        ("chave TLS", config.gateway.tls_keyfile),
        ("CA dos backends", config.gateway.backend_ca_file),
    ):
        if path is not None and not path.is_file():
            print(f"{label} ausente: {path}")
            ok = False
    for node in config.nodes:
        for label, path in (
            ("certificado TLS do nó", node.tls_certfile),
            ("chave TLS do nó", node.tls_keyfile),
        ):
            if path is not None and not path.is_file():
                print(f"nó {node.name}: {label} ausente: {path}")
                ok = False
    if config.router.enabled:
        try:
            router = SemanticRouter(config.router.examples_file, config.domains, config.router)
            print(f"avaliação roteador: {json.dumps(router.evaluation(), ensure_ascii=False)}")
        except ValueError as exc:
            print(f"roteador inválido: {exc}")
            ok = False
    print("configuração válida" if ok else "configuração carregada, mas há modelos ausentes ou divergentes")
    return 0 if ok else 1


def _cmd_token_create(args: argparse.Namespace) -> int:
    token = new_token()
    domains = [domain.strip() for domain in args.domains.split(",")]
    try:
        write_credential_file(
            Path(args.users_file),
            username=args.username,
            token=token,
            allowed_domains=domains,
            requests_per_minute=args.requests_per_minute,
            burst=args.burst,
            can_view_metrics=args.metrics,
            replace=args.replace,
        )
    except (OSError, ValueError) as exc:
        print(f"não foi possível provisionar token: {exc}", file=sys.stderr)
        return 2
    print(f"Token criado para usuário {args.username!r}. Guarde-o agora; ele não pode ser recuperado:")
    print(token)
    print(f"Hash gravado em {Path(args.users_file)} (permissões 0600).")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="llm-gateway", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="inicia o gateway")
    serve.add_argument("--config", required=True)
    serve.add_argument("--host")
    serve.add_argument("--port", type=int)
    serve.set_defaults(func=_cmd_serve)

    runtime = sub.add_parser("runtime", help="inicia um nó llama-server com a configuração do arquivo")
    runtime.add_argument("--config", required=True)
    runtime.add_argument("--node", required=True)
    runtime.set_defaults(func=_cmd_runtime)

    check = sub.add_parser("check-config", help="valida configuração e arquivos de modelo")
    check.add_argument("--config", required=True)
    check.add_argument(
        "--verify-models", action="store_true", help="calcula sha256 (lento para GGUF grandes)"
    )
    check.set_defaults(func=_cmd_check)

    token = sub.add_parser("token-create", help="cria token opaco e grava apenas o hash")
    token.add_argument("--users-file", required=True)
    token.add_argument("--username", required=True)
    token.add_argument("--domains", required=True, help="domínios separados por vírgula")
    token.add_argument("--requests-per-minute", type=float, default=30.0)
    token.add_argument("--burst", type=int, default=5)
    token.add_argument("--metrics", action="store_true", help="autoriza este usuário a consultar /metrics")
    token.add_argument("--replace", action="store_true", help="rotaciona credenciais do mesmo usuário")
    token.set_defaults(func=_cmd_token_create)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
