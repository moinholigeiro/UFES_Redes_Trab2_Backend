"""Utilitários compartilhados: configuração com backends simulados e servidor HTTP real."""

from __future__ import annotations

import socket
import threading
import time
from pathlib import Path
from typing import Any, Self

import pytest
import uvicorn

from llm_gateway.config import AppConfig

VALID_PRONTUARIO = (
    '{"idade":54,"sexo":"masculino","queixa_principal":"dor torácica",'
    '"diagnosticos":["suspeita de síndrome coronariana"],'
    '"medicamentos":[{"nome":"AAS","dose":"100 mg","via":"oral","frequencia":"diária"}],'
    '"alergias":["penicilina"],'
    '"sinais_vitais":{"pa":"150x90 mmHg","fc":null,"temp_c":null,"spo2":null}}'
)


def sim_config_dict(
    *,
    gateway: dict[str, Any] | None = None,
    nodes: list[dict[str, Any]] | None = None,
    domains: dict[str, Any] | None = None,
    policy: str = "round_robin",
) -> dict[str, Any]:
    models = {
        "sim-small": {
            "family": "sim",
            "quantization": "none",
            "source": "simulado",
            "license": "n/a",
        },
        "sim-big": {
            "family": "sim",
            "quantization": "none",
            "source": "simulado",
            "license": "n/a",
        },
    }
    default_domains = {
        "redes": {
            "description": "Redes simulado",
            "models": ["sim-small"],
            "prompt": "redes-v1",
            "output": "text",
            "temperature": 0.7,
            "default_max_output_tokens": 128,
            "max_output_tokens": 256,
        },
        "prontuario": {
            "description": "Prontuário simulado",
            "models": ["sim-big"],
            "prompt": "prontuario-v1",
            "output": "json_extraction",
            "schema": "prontuario-v1",
            "temperature": 0.0,
            "default_max_output_tokens": 256,
            "max_output_tokens": 512,
        },
    }
    default_nodes = [
        {
            "name": "redes-1",
            "kind": "simulated",
            "model": "sim-small",
            "max_inflight": 1,
            "max_queue": 4,
            "simulation": {
                "tokens_per_second": 200.0,
                "response": "Olá, este é um teste de streaming com acentuação: ação, é, 日本.",
            },
        },
        {
            "name": "prontuario-1",
            "kind": "simulated",
            "model": "sim-big",
            "max_inflight": 1,
            "max_queue": 4,
            "simulation": {"tokens_per_second": 200.0, "response": VALID_PRONTUARIO},
        },
    ]
    gw = {"allow_simulated_backends": True, "metrics_log": None, "heartbeat_interval_s": 0.2}
    gw.update(gateway or {})
    return {
        "gateway": gw,
        "balancing": {"policy": policy},
        "models": models,
        "domains": domains if domains is not None else default_domains,
        "nodes": nodes if nodes is not None else default_nodes,
    }


def build(raw: dict[str, Any]) -> AppConfig:
    return AppConfig.model_validate(raw)


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class ServerThread:
    """uvicorn em thread separada, para testar streaming e cancelamento com HTTP real."""

    def __init__(
        self,
        app: Any,
        port: int,
        *,
        ssl_certfile: Path | None = None,
        ssl_keyfile: Path | None = None,
    ) -> None:
        self.port = port
        self.app = app
        cfg = uvicorn.Config(
            app,
            host="127.0.0.1",
            port=port,
            log_level="warning",
            lifespan="on",
            ssl_certfile=str(ssl_certfile) if ssl_certfile else None,
            ssl_keyfile=str(ssl_keyfile) if ssl_keyfile else None,
        )
        self.server = uvicorn.Server(cfg)
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def __enter__(self) -> Self:
        self.thread.start()
        deadline = time.monotonic() + 10
        while not self.server.started:
            if time.monotonic() > deadline:
                raise RuntimeError("servidor de teste não iniciou")
            time.sleep(0.02)
        return self

    def __exit__(self, *exc: object) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=10)


@pytest.fixture
def serve(tmp_path: Path):
    """Factory: serve(raw_config_dict) -> ServerThread com gateway simulado."""
    from llm_gateway.api import create_app

    started: list[ServerThread] = []

    def _serve(raw: dict[str, Any]) -> ServerThread:
        raw = dict(raw)
        gw = dict(raw.get("gateway", {}))
        gw["metrics_log"] = str(tmp_path / "requests.jsonl")
        raw["gateway"] = gw
        server = ServerThread(create_app(build(raw)), free_port())
        server.__enter__()
        started.append(server)
        return server

    yield _serve
    for server in started:
        server.__exit__(None, None, None)
