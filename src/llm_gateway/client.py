"""Cliente de linha de comando: envia uma requisição, imprime o stream e mede tempos no cliente."""

from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import time
from pathlib import Path
from typing import Any

import httpx

from .protocol import iter_sse


def run_request(
    url: str,
    domain: str,
    text: str,
    max_output_tokens: int | None,
    *,
    timeout_s: float,
    echo: bool,
    ca_file: Path | None = None,
    bearer_token: str | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {"domain": domain, "input": text}
    if max_output_tokens is not None:
        body["max_output_tokens"] = max_output_tokens
    report: dict[str, Any] = {
        "meta": None,
        "deltas": 0,
        "result": None,
        "done": None,
        "error": None,
        "ttft_client_ms": None,
        "e2e_client_ms": None,
        "http_status": None,
    }
    started = time.monotonic()
    verify: bool | ssl.SSLContext = ssl.create_default_context(cafile=str(ca_file)) if ca_file else True
    headers = {"Accept": "text/event-stream"}
    if bearer_token:
        headers["Authorization"] = f"Bearer {bearer_token}"
    with (
        httpx.Client(timeout=timeout_s, verify=verify) as client,
        client.stream(
            "POST",
            url.rstrip("/") + "/v1/generate",
            json=body,
            headers=headers,
        ) as resp,
    ):
        report["http_status"] = resp.status_code
        if resp.status_code != 200:
            resp.read()
            report["error"] = resp.json().get("error", {"code": f"http_{resp.status_code}"})
            report["e2e_client_ms"] = round((time.monotonic() - started) * 1000, 3)
            return report
        for event, data in iter_sse(resp.iter_lines()):
            if event == "meta":
                report["meta"] = data
            elif event == "delta":
                if data["text"] and report["ttft_client_ms"] is None:
                    report["ttft_client_ms"] = round((time.monotonic() - started) * 1000, 3)
                report["deltas"] += 1
                if echo:
                    sys.stdout.write(data["text"])
                    sys.stdout.flush()
            elif event == "result":
                report["result"] = data
            elif event == "done":
                report["done"] = data
                break
            elif event == "error":
                report["error"] = data
                report["result"] = None
                break
        if report["done"] is None and report["error"] is None:
            report["error"] = {"code": "stream_interrupted", "message": "conexão encerrada sem done"}
            report["result"] = None
    if report["done"] is None:
        report["result"] = None
    report["e2e_client_ms"] = round((time.monotonic() - started) * 1000, 3)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="llm-gateway-client", description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8080")
    parser.add_argument("--domain", required=True)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", help="texto da requisição")
    source.add_argument("--input-file", type=Path, help="arquivo UTF-8 com o texto")
    parser.add_argument("--max-output-tokens", type=int)
    parser.add_argument("--timeout", type=float, default=600.0)
    parser.add_argument(
        "--ca", type=Path, help="CA bundle para validar TLS privado (nunca desabilita verify)"
    )
    parser.add_argument(
        "--token-env",
        default="LLM_GATEWAY_TOKEN",
        help="variável de ambiente com token Bearer (não o passe em argv)",
    )
    parser.add_argument("--json", action="store_true", help="imprime só o relatório JSON final")
    args = parser.parse_args(argv)

    text = args.input if args.input is not None else args.input_file.read_text(encoding="utf-8")
    try:
        report = run_request(
            args.url,
            args.domain,
            text,
            args.max_output_tokens,
            timeout_s=args.timeout,
            echo=not args.json,
            ca_file=args.ca,
            bearer_token=os.environ.get(args.token_env),
        )
    except httpx.HTTPError as err:
        print(f"falha de conexão: {err}", file=sys.stderr)
        return 3

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        sys.stdout.write("\n")
        if report["done"] is not None and report["error"] is None and report["result"] is not None:
            print(json.dumps(report["result"]["data"], ensure_ascii=False, indent=2))
        summary = {k: report[k] for k in ("ttft_client_ms", "e2e_client_ms", "deltas", "done", "error")}
        print(json.dumps(summary, ensure_ascii=False), file=sys.stderr)
    return 0 if report["done"] is not None and report["error"] is None else 1


if __name__ == "__main__":
    raise SystemExit(main())
