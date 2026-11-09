"""Backend para `llama-server` (llama.cpp), via /v1/chat/completions com stream=true."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

import httpx

from ..clinical import json_schema_for
from ..config import NodeConfig
from ..jobs import JobError
from .base import Chunk, Delta, Finish

if TYPE_CHECKING:
    from ..jobs import Job


class LlamaServerBackend:
    def __init__(self, node: NodeConfig, client: httpx.AsyncClient) -> None:
        if node.url is None:
            raise ValueError(f"nó {node.name!r} sem url")
        self._node = node
        self._client = client
        self._endpoint = node.url.rstrip("/") + "/v1/chat/completions"
        self._headers: dict[str, str] = {}
        if node.api_key_file is not None:
            key = node.api_key_file.read_text(encoding="utf-8").strip()
            if not key:
                raise ValueError(f"arquivo de chave vazio para o nó {node.name!r}")
            self._headers["Authorization"] = f"Bearer {key}"

    def _body(self, job: Job) -> dict[str, Any]:
        body: dict[str, Any] = {
            "messages": job.messages,
            "stream": True,
            "stream_options": {"include_usage": True},
            "max_tokens": job.max_output_tokens,
            **job.sampling,
        }
        if job.schema is not None:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": job.schema, "schema": json_schema_for(job.schema)},
            }
        return body

    async def stream(self, job: Job) -> AsyncIterator[Chunk]:
        finish: str | None = None
        usage: dict[str, Any] | None = None
        saw_done = False
        try:
            async with self._client.stream(
                "POST", self._endpoint, json=self._body(job), headers=self._headers
            ) as resp:
                if resp.status_code != 200:
                    preview = bytearray()
                    async for block in resp.aiter_bytes():
                        preview.extend(block[: 4096 - len(preview)])
                        if len(preview) >= 4096:
                            break
                    if resp.status_code == 401:
                        raise JobError("backend_error", f"nó {self._node.name} recusou a chave de API")
                    code = "backend_unavailable" if resp.status_code == 503 else "backend_error"
                    raise JobError(code, f"nó {self._node.name} respondeu HTTP {resp.status_code}")
                async for line in resp.aiter_lines():
                    if len(line.encode("utf-8", errors="replace")) > self._node.max_frame_bytes:
                        raise JobError("backend_protocol_error", "nó enviou frame acima do limite")
                    if not line.startswith("data:"):
                        continue
                    payload = line[len("data:") :].strip()
                    if payload == "[DONE]":
                        if saw_done:
                            raise JobError("backend_protocol_error", "nó enviou múltiplas terminações")
                        saw_done = True
                        continue
                    if saw_done:
                        raise JobError("backend_protocol_error", "nó enviou dados após [DONE]")
                    event = json.loads(payload)
                    if not isinstance(event, dict):
                        raise JobError("backend_protocol_error", "nó enviou frame inválido")
                    if "error" in event:
                        raise JobError("backend_error", f"nó {self._node.name} reportou erro interno")
                    if finish is not None and event.get("choices"):
                        raise JobError("backend_protocol_error", "nó enviou choices após finish")
                    if event.get("usage"):
                        if not isinstance(event["usage"], dict):
                            raise JobError("backend_protocol_error", "nó enviou usage inválido")
                        usage = event["usage"]
                    choices = event.get("choices")
                    if not isinstance(choices, list):
                        raise JobError("backend_protocol_error", "nó enviou choices inválido")
                    for choice in choices:
                        if not isinstance(choice, dict):
                            raise JobError("backend_protocol_error", "nó enviou choice inválido")
                        delta = choice.get("delta")
                        if not isinstance(delta, dict):
                            raise JobError("backend_protocol_error", "nó enviou delta inválido")
                        content = delta.get("content")
                        if content is not None and not isinstance(content, str):
                            raise JobError("backend_protocol_error", "nó enviou conteúdo inválido")
                        if content:
                            yield Delta(content)
                        reason = choice.get("finish_reason")
                        if reason is not None:
                            if reason not in {"stop", "length"} or finish is not None:
                                raise JobError("backend_protocol_error", "nó enviou término inválido")
                            finish = reason
                if not saw_done or finish is None:
                    raise JobError("incomplete_stream", "stream interno terminou sem [DONE] e finish válidos")
                if usage is not None:
                    token_count = usage.get("completion_tokens")
                    if token_count is not None and (
                        isinstance(token_count, bool) or not isinstance(token_count, int) or token_count < 0
                    ):
                        raise JobError("backend_protocol_error", "nó enviou contagem de tokens inválida")
        except httpx.ConnectError as err:
            raise JobError("backend_unavailable", f"nó {self._node.name} inacessível") from err
        except httpx.TimeoutException as err:
            raise JobError("backend_timeout", f"nó {self._node.name} sem resposta no prazo") from err
        except httpx.HTTPError as err:
            raise JobError(
                "backend_transport_error", f"falha de transporte com o nó {self._node.name}"
            ) from err
        except (json.JSONDecodeError, UnicodeDecodeError) as err:
            raise JobError("backend_protocol_error", f"resposta inválida do nó {self._node.name}") from err
        yield Finish(finish, usage)
