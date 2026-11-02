"""Backends de inferência disponíveis para os nós."""

from __future__ import annotations

import httpx

from ..config import NodeConfig
from .base import Backend, Chunk, Delta, Finish
from .llama_server import LlamaServerBackend
from .simulated import SimulatedBackend

__all__ = [
    "Backend",
    "Chunk",
    "Delta",
    "Finish",
    "LlamaServerBackend",
    "SimulatedBackend",
    "make_backend",
]


def make_backend(node: NodeConfig, client: httpx.AsyncClient) -> Backend:
    if node.kind == "llama_server":
        return LlamaServerBackend(node, client)
    if node.simulation is None:
        raise ValueError(f"nó {node.name!r} simulado sem configuração")
    return SimulatedBackend(node.simulation)
