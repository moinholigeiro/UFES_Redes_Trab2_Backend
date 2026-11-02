"""Configuração validada do gateway (arquivo TOML)."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .clinical import SCHEMAS
from .prompts import PROMPTS


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class GatewayConfig(_Strict):
    host: str = "127.0.0.1"
    port: int = Field(8080, ge=1, le=65535)
    max_request_bytes: int = Field(65536, ge=1024)
    request_body_timeout_s: float = Field(15.0, gt=0)
    max_input_chars: int = Field(12000, ge=1)
    max_output_tokens_limit: int = Field(2048, ge=1)
    request_deadline_s: float = Field(600.0, gt=0)
    queue_timeout_s: float = Field(120.0, gt=0)
    client_stall_timeout_s: float = Field(30.0, gt=0)
    backend_read_timeout_s: float = Field(60.0, gt=0)
    health_check_interval_s: float = Field(2.0, gt=0)
    health_check_timeout_s: float = Field(1.0, gt=0)
    event_buffer_size: int = Field(64, ge=1)
    heartbeat_interval_s: float = Field(15.0, gt=0)
    metrics_log: Path | None = Path("artifacts/logs/requests.jsonl")
    allow_simulated_backends: bool = False
    tls_certfile: Path | None = None
    tls_keyfile: Path | None = None
    backend_ca_file: Path | None = None

    @model_validator(mode="after")
    def _tls_pair(self) -> GatewayConfig:
        if (self.tls_certfile is None) != (self.tls_keyfile is None):
            raise ValueError("tls_certfile e tls_keyfile devem ser informados juntos")
        return self


class SecurityConfig(_Strict):
    enabled: bool = False
    users_file: Path | None = None
    require_tls: bool = False

    @model_validator(mode="after")
    def _check(self) -> SecurityConfig:
        if self.enabled and self.users_file is None:
            raise ValueError("security.enabled exige security.users_file")
        if self.require_tls and not self.enabled:
            raise ValueError("security.require_tls exige security.enabled")
        return self


class RouterConfig(_Strict):
    enabled: bool = False
    examples_file: Path = Path("data/routing_examples.jsonl")
    confidence_threshold: float = Field(0.60, gt=0.0, le=1.0)
    complexity_confidence_threshold: float = Field(0.55, gt=0.0, le=1.0)
    test_fraction: float = Field(0.25, ge=0.1, le=0.4)
    random_seed: int = Field(42, ge=0)


class BalancingConfig(_Strict):
    policy: Literal["round_robin", "least_loaded", "least_latency"] = "round_robin"
    max_failover_attempts: int = Field(1, ge=0, le=3)


class ModelConfig(_Strict):
    family: str
    quantization: str
    source: str
    license: str
    sha256: str | None = None
    context_tokens: int = Field(4096, ge=256)

    @model_validator(mode="after")
    def _check_hash(self) -> ModelConfig:
        if self.sha256 is not None and (
            len(self.sha256) != 64 or any(char not in "0123456789abcdefABCDEF" for char in self.sha256)
        ):
            raise ValueError("sha256 do modelo deve ter 64 caracteres hexadecimais")
        return self


class DomainConfig(_Strict):
    description: str
    models: list[str] = Field(min_length=1)
    default_model: str | None = None
    model_by_complexity: dict[Literal["simple", "complex"], str] = Field(default_factory=dict)
    prompt: str
    output: Literal["text", "json_extraction"] = "text"
    schema_name: str | None = Field(None, alias="schema")
    temperature: float = Field(0.7, ge=0.0, le=2.0)
    top_p: float = Field(1.0, gt=0.0, le=1.0)
    top_k: int = Field(0, ge=0)
    default_max_output_tokens: int = Field(512, ge=1)
    max_output_tokens: int = Field(1024, ge=1)

    @model_validator(mode="after")
    def _check(self) -> DomainConfig:
        if self.prompt not in PROMPTS:
            raise ValueError(f"prompt desconhecido: {self.prompt!r}")
        if self.output == "json_extraction":
            if self.schema_name not in SCHEMAS:
                raise ValueError("domínio json_extraction exige schema conhecido")
        elif self.schema_name is not None:
            raise ValueError("schema só é permitido em domínio json_extraction")
        if self.default_max_output_tokens > self.max_output_tokens:
            raise ValueError("default_max_output_tokens excede max_output_tokens")
        if self.default_model is not None and self.default_model not in self.models:
            raise ValueError("default_model deve estar na lista de models do domínio")
        if not set(self.model_by_complexity.values()).issubset(self.models):
            raise ValueError("model_by_complexity deve apontar para modelos permitidos pelo domínio")
        return self


class SimulationConfig(_Strict):
    """Comportamento de backend simulado. Só aceito com allow_simulated_backends=true."""

    tokens_per_second: float = Field(50.0, gt=0)
    response: str = "Resposta simulada."
    startup_delay_s: float = Field(0.0, ge=0)
    fail_after_deltas: int | None = Field(None, ge=0)


class NodeConfig(_Strict):
    name: str = Field(pattern=r"^[A-Za-z0-9_-]+$", min_length=1, max_length=64)
    kind: Literal["llama_server", "simulated"] = "llama_server"
    url: str | None = None
    model: str
    max_inflight: int = Field(1, ge=1)
    max_queue: int = Field(16, ge=1)
    max_frame_bytes: int = Field(262_144, ge=1024)
    max_output_bytes: int = Field(2_097_152, ge=1024)
    chat_template_kwargs: dict[str, Any] = Field(default_factory=dict)
    simulation: SimulationConfig | None = None

    @model_validator(mode="after")
    def _check(self) -> NodeConfig:
        if self.kind == "llama_server":
            if not self.url or not self.url.startswith(("http://", "https://")):
                raise ValueError("nó llama_server exige url http(s)")
            if self.simulation is not None:
                raise ValueError("simulation só existe em nó simulated")
        else:
            if self.simulation is None:
                raise ValueError("nó simulated exige bloco simulation")
        return self


class AppConfig(_Strict):
    gateway: GatewayConfig = Field(default_factory=GatewayConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    router: RouterConfig = Field(default_factory=RouterConfig)
    balancing: BalancingConfig = Field(default_factory=BalancingConfig)
    models: dict[str, ModelConfig] = Field(default_factory=dict)
    domains: dict[str, DomainConfig]
    nodes: list[NodeConfig] = Field(min_length=1)

    @model_validator(mode="after")
    def _check(self) -> AppConfig:
        if self.security.require_tls and self.gateway.tls_certfile is None:
            raise ValueError("security.require_tls exige gateway.tls_certfile e tls_keyfile")
        names = [n.name for n in self.nodes]
        if len(set(names)) != len(names):
            raise ValueError("nomes de nós duplicados")
        for node in self.nodes:
            if node.model not in self.models:
                raise ValueError(f"nó {node.name!r} usa modelo não declarado: {node.model!r}")
            if node.kind == "simulated" and not self.gateway.allow_simulated_backends:
                raise ValueError(
                    f"nó {node.name!r} é simulado; habilite gateway.allow_simulated_backends só para testes"
                )
        for dname, dom in self.domains.items():
            for m in dom.models:
                if m not in self.models:
                    raise ValueError(f"domínio {dname!r} usa modelo não declarado: {m!r}")
                if not any(n.model == m for n in self.nodes):
                    raise ValueError(f"domínio {dname!r} não tem nó para o modelo {m!r}")
            if dom.max_output_tokens > self.gateway.max_output_tokens_limit:
                raise ValueError(f"domínio {dname!r} excede gateway.max_output_tokens_limit")
            if not any(n.model in dom.models for n in self.nodes):
                raise ValueError(f"domínio {dname!r} não tem nó elegível")
            if self.router.enabled and set(dom.model_by_complexity) != {"simple", "complex"}:
                raise ValueError(f"roteador habilitado exige modelos simple e complex no domínio {dname!r}")
        for node in self.nodes:
            if not any(node.model in d.models for d in self.domains.values()):
                raise ValueError(f"nó {node.name!r} não atende nenhum domínio")
        return self


def load_config(path: str | Path) -> AppConfig:
    with Path(path).open("rb") as fh:
        raw = tomllib.load(fh)
    return AppConfig.model_validate(raw)
