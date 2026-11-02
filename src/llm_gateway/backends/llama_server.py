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
        try:
            async with self._client.stream("POST", self._endpoint, json=self._body(job)) as resp:
                if resp.status_code != 200:
                    await resp.aread()
                    code = "backend_unavailable" if resp.status_code == 503 else "backend_error"
                    raise JobError(code, f"nó {self._node.name} respondeu HTTP {resp.status_code}")
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    payload = line[len("data:") :].strip()
                    if payload == "[DONE]":
                        break
                    event = json.loads(payload)
                    if "error" in event:
                        raise JobError("backend_error", f"nó {self._node.name} reportou erro interno")
                    if event.get("usage"):
                        usage = event["usage"]
                    for choice in event.get("choices") or []:
                        content = (choice.get("delta") or {}).get("content")
                        if content:
                            yield Delta(content)
                        if choice.get("finish_reason"):
                            finish = choice["finish_reason"]
        except httpx.ConnectError as err:
            raise JobError("backend_unavailable", f"nó {self._node.name} inacessível") from err
        except httpx.TimeoutException as err:
            raise JobError("backend_timeout", f"nó {self._node.name} sem resposta no prazo") from err
        except (httpx.HTTPError, json.JSONDecodeError) as err:
            raise JobError("backend_error", f"falha de transporte com o nó {self._node.name}") from err
        yield Finish(finish or "eof", usage)
