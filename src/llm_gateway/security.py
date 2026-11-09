"""Token auth, domain authorization and per-user token-bucket rate limiting.

The credential file contains only SHA-256 digests of high-entropy opaque tokens.
Plain tokens are returned only at provisioning time and are never logged.
"""

from __future__ import annotations

import hashlib
import hmac
import math
import secrets
import time
import tomllib
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class CredentialError(ValueError):
    pass


class RateLimitExceeded(Exception):
    def __init__(self, retry_after_s: int) -> None:
        self.retry_after_s = max(1, retry_after_s)
        super().__init__("rate limit exceeded")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class UserCredential(_Strict):
    token_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    allowed_domains: list[str] = Field(min_length=1)
    requests_per_minute: float = Field(gt=0)
    burst: int = Field(ge=1)
    can_view_metrics: bool = False


class CredentialFile(_Strict):
    users: dict[str, UserCredential] = Field(min_length=1)


@dataclass(frozen=True)
class Principal:
    username: str
    allowed_domains: frozenset[str]
    can_view_metrics: bool
    pseudonym: str


def load_credentials(path: Path, known_domains: set[str]) -> CredentialFile:
    try:
        with path.open("rb") as fh:
            raw: dict[str, Any] = tomllib.load(fh)
        credentials = CredentialFile.model_validate(raw)
    except (OSError, ValidationError, tomllib.TOMLDecodeError) as exc:
        raise CredentialError(f"não foi possível carregar credenciais de {path}") from exc
    seen: set[str] = set()
    for username, user in credentials.users.items():
        if not username or len(username) > 64:
            raise CredentialError("nome de usuário inválido no arquivo de credenciais")
        if any(domain not in known_domains for domain in user.allowed_domains):
            raise CredentialError(f"usuário {username!r} referencia domínio desconhecido")
        if user.token_sha256 in seen:
            raise CredentialError("hash de token duplicado no arquivo de credenciais")
        seen.add(user.token_sha256)
    return credentials


class TokenBucket:
    """Bucket de tokens por usuário, seguro no event loop single-worker do gateway."""

    def __init__(self, rate_per_minute: float, burst: int) -> None:
        self.capacity = float(burst)
        self.refill_per_second = rate_per_minute / 60.0
        self.tokens = self.capacity
        self.updated_at = time.monotonic()

    def consume(self, now: float | None = None) -> None:
        current = time.monotonic() if now is None else now
        elapsed = max(0.0, current - self.updated_at)
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_per_second)
        self.updated_at = current
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return
        wait_s = (1.0 - self.tokens) / self.refill_per_second
        raise RateLimitExceeded(int(wait_s + 0.999))


class SecurityManager:
    def __init__(self, credentials: CredentialFile) -> None:
        self._credentials = credentials
        self._buckets: dict[str, TokenBucket] = {}
        self._audit_key = secrets.token_bytes(32)

    def authenticate(self, authorization: str | None) -> Principal | None:
        if not authorization:
            raise PermissionError("missing_token")
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token or " " in token:
            raise PermissionError("invalid_token")
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        found: tuple[str, UserCredential] | None = None
        # Compare every configured hash to reduce username-dependent timing differences.
        for username, credential in self._credentials.users.items():
            if hmac.compare_digest(digest, credential.token_sha256):
                found = (username, credential)
        if found is None:
            raise PermissionError("invalid_token")
        username, credential = found
        pseudonym = hmac.new(self._audit_key, username.encode("utf-8"), hashlib.sha256).hexdigest()[:16]
        return Principal(
            username=username,
            allowed_domains=frozenset(credential.allowed_domains),
            can_view_metrics=credential.can_view_metrics,
            pseudonym=pseudonym,
        )

    def authorize_domain(self, principal: Principal, domain: str) -> None:
        if domain not in principal.allowed_domains:
            raise PermissionError("domain_forbidden")

    def consume_request(self, principal: Principal) -> None:
        credential = self._credentials.users[principal.username]
        bucket = self._buckets.get(principal.username)
        if bucket is None:
            bucket = TokenBucket(credential.requests_per_minute, credential.burst)
            self._buckets[principal.username] = bucket
        bucket.consume()

    @staticmethod
    def allow_metrics(principal: Principal) -> bool:
        return principal.can_view_metrics


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_token() -> str:
    """256 bits of entropy, URL-safe for use in Authorization: Bearer."""
    return secrets.token_urlsafe(32)


def write_credential_file(
    path: Path,
    *,
    username: str,
    token: str,
    allowed_domains: list[str],
    requests_per_minute: float,
    burst: int,
    can_view_metrics: bool,
    replace: bool = False,
) -> None:
    """Atomically write/replace one user's credential with restrictive permissions."""
    import json
    import os
    import re
    import tempfile

    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", username):
        raise ValueError("username aceita apenas letras, números, ponto, hífen e underscore")
    if not allowed_domains or len(set(allowed_domains)) != len(allowed_domains):
        raise ValueError("informe domínios permitidos únicos")
    if not math.isfinite(requests_per_minute) or requests_per_minute <= 0 or burst < 1:
        raise ValueError("rate e burst devem ser positivos")

    current: dict[str, Any] = {"users": {}}
    if path.exists():
        with path.open("rb") as fh:
            current = tomllib.load(fh)
        current.setdefault("users", {})
    users = current["users"]
    if username in users and not replace:
        raise FileExistsError(f"usuário {username!r} já existe; use --replace para rotacionar o token")
    users[username] = {
        "token_sha256": token_digest(token),
        "allowed_domains": allowed_domains,
        "requests_per_minute": requests_per_minute,
        "burst": burst,
        "can_view_metrics": can_view_metrics,
    }

    lines: list[str] = []
    for name, entry in users.items():
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", name):
            raise ValueError(f"nome inválido no arquivo existente: {name!r}")
        lines.extend(
            [
                f"[users.{json.dumps(name)}]",
                f"token_sha256 = {json.dumps(entry['token_sha256'])}",
                f"allowed_domains = {json.dumps(entry['allowed_domains'])}",
                f"requests_per_minute = {float(entry['requests_per_minute'])}",
                f"burst = {int(entry['burst'])}",
                f"can_view_metrics = {'true' if entry.get('can_view_metrics', False) else 'false'}",
                "",
            ]
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent, text=True)
    try:
        # O `with` fecha o descritor mesmo em erro; sem isso, o unlink abaixo falha no Windows.
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            if hasattr(os, "fchmod"):  # POSIX: restringe antes de escrever o segredo
                os.fchmod(fh.fileno(), 0o600)
            fh.write("\n".join(lines))
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(temp_name, path)
        # No Windows, chmod só controla somente-leitura; o modo 0600 vale em Linux e macOS.
        os.chmod(path, 0o600)
    except Exception:
        with suppress(FileNotFoundError):
            os.unlink(temp_name)
        raise
