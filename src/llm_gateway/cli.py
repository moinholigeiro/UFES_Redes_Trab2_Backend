"""Linha de comando do gateway: serve, check-config e token-create."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .api import CONFIG_ENV
from .config import AppConfig, load_config
from .routing import SemanticRouter
from .security import load_credentials, new_token, write_credential_file


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


def _cmd_check(args: argparse.Namespace) -> int:
    config: AppConfig = load_config(args.config)
    ok = True
    for name, model in config.models.items():
        print(f"modelo {name}: {model.family} {model.quantization} sha256={model.sha256 or 'não informado'}")
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
    if config.router.enabled:
        try:
            router = SemanticRouter(config.router.examples_file, config.domains, config.router)
            print(f"avaliação roteador: {json.dumps(router.evaluation(), ensure_ascii=False)}")
        except ValueError as exc:
            print(f"roteador inválido: {exc}")
            ok = False
    print("configuração do gateway válida" if ok else "configuração inválida")
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

    check = sub.add_parser("check-config", help="valida configuração e arquivos de modelo")
    check.add_argument("--config", required=True)
    check.add_argument(
        "--verify-models", action="store_true", help="pesos são verificados no repositório LLM"
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
