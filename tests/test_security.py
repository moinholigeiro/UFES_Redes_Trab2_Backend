"""Testes de auth por bearer, autorização, rate limit, credenciais e TLS real."""

from __future__ import annotations

import json
import os
import ssl
import subprocess
from pathlib import Path

import httpx
import pytest

from llm_gateway.api import create_app
from llm_gateway.protocol import iter_sse
from llm_gateway.security import (
    CredentialError,
    RateLimitExceeded,
    SecurityManager,
    TokenBucket,
    load_credentials,
    new_token,
    token_digest,
    write_credential_file,
)

from .conftest import ServerThread, build, free_port, sim_config_dict


def provision(
    path: Path,
    token: str,
    *,
    domains: list[str] | None = None,
    rpm: float = 30,
    burst: int = 5,
    metrics: bool = False,
) -> None:
    write_credential_file(
        path,
        username="aluno.teste",
        token=token,
        allowed_domains=domains or ["redes"],
        requests_per_minute=rpm,
        burst=burst,
        can_view_metrics=metrics,
    )


def secure_raw(users_file: Path, *, rpm: float = 30, burst: int = 5, metrics: bool = False) -> dict:
    token = new_token()
    provision(users_file, token, rpm=rpm, burst=burst, metrics=metrics)
    raw = sim_config_dict()
    raw["security"] = {"enabled": True, "users_file": str(users_file), "require_tls": False}
    return raw, token


def test_opaque_token_file_contains_hash_only_and_mode_0600(tmp_path: Path):
    path = tmp_path / "secrets" / "users.toml"
    token = new_token()
    provision(path, token)
    text = path.read_text(encoding="utf-8")
    assert token not in text
    assert token_digest(token) in text
    assert os.stat(path).st_mode & 0o777 == 0o600
    assert len(token) >= 40
    assert '[users."aluno.teste"]' in text


def test_duplicate_user_requires_explicit_rotation(tmp_path: Path):
    path = tmp_path / "users.toml"
    provision(path, new_token())
    with pytest.raises(FileExistsError):
        provision(path, new_token())
    rotated = new_token()
    write_credential_file(
        path,
        username="aluno.teste",
        token=rotated,
        allowed_domains=["redes"],
        requests_per_minute=30,
        burst=5,
        can_view_metrics=False,
        replace=True,
    )
    credentials = load_credentials(path, {"redes", "prontuario"})
    assert credentials.users["aluno.teste"].token_sha256 == token_digest(rotated)


def test_unknown_domains_in_credentials_fail_closed(tmp_path: Path):
    path = tmp_path / "users.toml"
    provision(path, new_token(), domains=["admin"])
    with pytest.raises(CredentialError, match="domínio desconhecido"):
        load_credentials(path, {"redes", "prontuario"})


def test_authentication_uses_bearer_hash_and_domain_permissions(tmp_path: Path):
    path = tmp_path / "users.toml"
    token = new_token()
    provision(path, token, domains=["redes"])
    manager = SecurityManager(load_credentials(path, {"redes", "prontuario"}))
    with pytest.raises(PermissionError, match="missing_token"):
        manager.authenticate(None)
    with pytest.raises(PermissionError, match="invalid_token"):
        manager.authenticate("Bearer wrong")
    principal = manager.authenticate(f"Bearer {token}")
    assert principal is not None
    assert principal.allowed_domains == {"redes"}
    assert principal.username == "aluno.teste"
    assert token not in principal.pseudonym
    manager.authorize_domain(principal, "redes")
    with pytest.raises(PermissionError, match="domain_forbidden"):
        manager.authorize_domain(principal, "prontuario")


def test_token_bucket_refills_and_returns_retry_time():
    bucket = TokenBucket(rate_per_minute=60, burst=2)
    bucket.consume(now=10)
    bucket.consume(now=10)
    with pytest.raises(RateLimitExceeded) as exc:
        bucket.consume(now=10)
    assert exc.value.retry_after_s == 1
    bucket.consume(now=11)


def test_write_credentials_rejects_infinite_rate(tmp_path: Path):
    with pytest.raises(ValueError, match="positivos"):
        write_credential_file(
            tmp_path / "users.toml",
            username="aluno",
            token=new_token(),
            allowed_domains=["redes"],
            requests_per_minute=float("inf"),
            burst=1,
            can_view_metrics=False,
        )


def test_http_requires_token_authorizes_domain_and_protects_metrics(serve, tmp_path: Path):
    users_file = tmp_path / "users.toml"
    raw, token = secure_raw(users_file)
    server = serve(raw)
    headers = {"Authorization": f"Bearer {token}"}
    with httpx.Client(base_url=server.url, timeout=5) as client:
        missing = client.post("/v1/generate", json={"domain": "redes", "input": "oi"})
        assert missing.status_code == 401
        assert missing.headers["www-authenticate"] == "Bearer"
        wrong = client.post(
            "/v1/generate",
            json={"domain": "redes", "input": "oi"},
            headers={"Authorization": "Bearer incorreto"},
        )
        assert wrong.status_code == 401

        denied = client.post(
            "/v1/generate",
            json={"domain": "prontuario", "input": "texto"},
            headers=headers,
        )
        assert denied.status_code == 403
        assert denied.json()["error"]["code"] == "domain_forbidden"

        metrics = client.get("/metrics", headers=headers)
        assert metrics.status_code == 403
        assert metrics.json()["error"]["code"] == "metrics_forbidden"

        stream = client.stream(
            "POST",
            "/v1/generate",
            json={"domain": "redes", "input": "oi"},
            headers={**headers, "Accept": "text/event-stream"},
        )
        with stream as resp:
            assert resp.status_code == 200
            request_id = resp.headers["x-request-id"]
            events = list(iter_sse(resp.iter_lines()))
        assert events[-1][0] == "done"
        assert events[0][1]["request_id"] == request_id
        assert events[-1][1]["request_id"] == request_id
    log_text = (tmp_path / "requests.jsonl").read_text(encoding="utf-8")
    row = json.loads(log_text.splitlines()[-1])
    assert row["user_pseudonym"]
    assert token not in log_text and "aluno.teste" not in log_text


def test_rate_limit_returns_429_and_retry_after(serve, tmp_path: Path):
    raw, token = secure_raw(tmp_path / "users.toml", rpm=0.01, burst=1)
    server = serve(raw)
    headers = {"Authorization": f"Bearer {token}"}
    body = {"domain": "redes", "input": "oi"}
    with httpx.Client(base_url=server.url, timeout=5) as client:
        with client.stream("POST", "/v1/generate", json=body, headers=headers) as resp:
            assert resp.status_code == 200
            list(resp.iter_lines())
        limited = client.post("/v1/generate", json=body, headers=headers)
    assert limited.status_code == 429
    assert limited.headers["retry-after"] == "6000"
    assert limited.json()["error"]["code"] == "rate_limited"


def test_metrics_access_requires_explicit_user_permission(serve, tmp_path: Path):
    raw, token = secure_raw(tmp_path / "users.toml", metrics=True)
    server = serve(raw)
    response = httpx.get(f"{server.url}/metrics", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert "nodes" in response.json()


def test_auto_routing_cannot_bypass_domain_authorization(serve, tmp_path: Path):
    from .test_routing import auto_api_config

    users_file = tmp_path / "users.toml"
    token = new_token()
    provision(users_file, token, domains=["redes"])
    raw = auto_api_config()
    raw["security"] = {"enabled": True, "users_file": str(users_file), "require_tls": False}
    server = serve(raw)
    clinical_text = (
        "Extraia dose de medicamento deste prontuário sintético: "
        "metformina 850 mg via oral duas vezes ao dia."
    )
    response = httpx.post(
        f"{server.url}/v1/generate",
        json={"domain": "auto", "input": clinical_text},
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "domain_forbidden"
    assert (tmp_path / "requests.jsonl").read_text(encoding="utf-8") == ""


def test_tls_trusts_configured_ca_and_rejects_untrusted_certificate(tmp_path: Path):
    cert_dir = tmp_path / "tls"
    script = Path(__file__).resolve().parents[1] / "scripts" / "generate-local-ca.sh"
    subprocess.run(["bash", str(script), str(cert_dir)], check=True, capture_output=True, text=True)
    users_file = tmp_path / "users.toml"
    token = new_token()
    provision(users_file, token, metrics=True)
    raw = sim_config_dict()
    raw["security"] = {"enabled": True, "users_file": str(users_file), "require_tls": True}
    raw["gateway"].update(
        {
            "tls_certfile": str(cert_dir / "gateway.crt"),
            "tls_keyfile": str(cert_dir / "gateway.key"),
        }
    )
    app = create_app(build(raw))
    with ServerThread(
        app,
        free_port(),
        ssl_certfile=cert_dir / "gateway.crt",
        ssl_keyfile=cert_dir / "gateway.key",
    ) as server:
        url = server.url.replace("http://", "https://", 1)
        verify = ssl.create_default_context(cafile=str(cert_dir / "ca.crt"))
        with httpx.Client(verify=verify, timeout=5) as trusted:
            health = trusted.get(f"{url}/health")
            assert health.status_code == 200
            denied = trusted.get(f"{url}/metrics")
            assert denied.status_code == 401
            authorized = trusted.get(f"{url}/metrics", headers={"Authorization": f"Bearer {token}"})
            assert authorized.status_code == 200
        with pytest.raises(httpx.ConnectError):
            httpx.get(f"{url}/health", timeout=3)
