"""Backend llama-server com transporte simulado (MockTransport): protocolo SSE OpenAI-compatível."""

from __future__ import annotations

import asyncio
import json
import time
import uuid

import httpx
import pytest

from llm_gateway.backends.base import Delta, Finish
from llm_gateway.backends.llama_server import LlamaServerBackend
from llm_gateway.config import NodeConfig
from llm_gateway.jobs import Job, JobError

PRONT_NODE = NodeConfig(
    name="pront", kind="llama_server", url="http://nó.test:8102", model="m", chat_template_kwargs={}
)


def make_job(schema: str | None = None) -> Job:
    now = time.monotonic()
    return Job(
        request_id=uuid.uuid4().hex,
        domain="prontuario" if schema else "redes",
        prompt="prontuario-v1" if schema else "redes-v1",
        prompt_hash="0" * 16,
        output="json_extraction" if schema else "text",
        schema=schema,
        messages=[{"role": "system", "content": "s"}, {"role": "user", "content": "u"}],
        sampling={"temperature": 0.0, "top_p": 1.0, "top_k": 0},
        max_output_tokens=32,
        input_chars=1,
        events=asyncio.Queue(),
        enqueued_at=now,
        deadline=now + 30,
    )


def sse_body(*chunks: dict | str) -> bytes:
    lines = []
    for chunk in chunks:
        payload = chunk if isinstance(chunk, str) else json.dumps(chunk, ensure_ascii=False)
        lines.append(f"data: {payload}\n\n")
    return "".join(lines).encode("utf-8")


def content(text: str) -> dict:
    return {"choices": [{"index": 0, "delta": {"content": text}, "finish_reason": None}]}


STOP = {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}
USAGE = {"choices": [], "usage": {"completion_tokens": 3, "prompt_tokens": 7}}


async def collect(backend: LlamaServerBackend, job: Job) -> list:
    out = []
    async for chunk in backend.stream(job):
        out.append(chunk)
    return out


def backend_with(handler) -> LlamaServerBackend:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return LlamaServerBackend(PRONT_NODE, client)


async def test_streams_deltas_usage_and_finish_in_order():
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["stream"] is True
        assert body["stream_options"] == {"include_usage": True}
        assert "response_format" not in body
        return httpx.Response(200, content=sse_body(content("Olá"), content(" mundo"), STOP, USAGE, "[DONE]"))

    chunks = await collect(backend_with(handler), make_job())
    assert chunks == [
        Delta("Olá"),
        Delta(" mundo"),
        Finish("stop", {"completion_tokens": 3, "prompt_tokens": 7}),
    ]


async def test_json_domain_sends_schema_as_response_format():
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        fmt = body["response_format"]
        assert fmt["type"] == "json_schema"
        assert fmt["json_schema"]["name"] == "prontuario-v1"
        assert fmt["json_schema"]["schema"]["additionalProperties"] is False
        return httpx.Response(200, content=sse_body(content("{}"), STOP, "[DONE]"))

    await collect(backend_with(handler), make_job(schema="prontuario-v1"))


async def test_eof_without_finish_reason_is_reported_as_eof():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=sse_body(content("parcial")))

    chunks = await collect(backend_with(handler), make_job())
    assert chunks[-1] == Finish("eof", None)


async def test_http_503_is_backend_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "loading"})

    with pytest.raises(JobError) as exc:
        await collect(backend_with(handler), make_job())
    assert exc.value.code == "backend_unavailable"


async def test_http_500_is_backend_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    with pytest.raises(JobError) as exc:
        await collect(backend_with(handler), make_job())
    assert exc.value.code == "backend_error"


async def test_connection_refused_is_backend_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("recusada", request=request)

    with pytest.raises(JobError) as exc:
        await collect(backend_with(handler), make_job())
    assert exc.value.code == "backend_unavailable"


async def test_read_timeout_is_backend_timeout():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("demorou", request=request)

    with pytest.raises(JobError) as exc:
        await collect(backend_with(handler), make_job())
    assert exc.value.code == "backend_timeout"


async def test_in_stream_error_object_is_backend_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=sse_body(content("x"), {"error": {"message": "oops"}}))

    with pytest.raises(JobError) as exc:
        await collect(backend_with(handler), make_job())
    assert exc.value.code == "backend_error"
