from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from llm_gateway.clinical import json_schema_for, validate_output
from llm_gateway.protocol import GenerateRequest, iter_sse, sse_comment, sse_encode


def test_sse_roundtrip_preserves_unicode_and_skips_comments():
    wire = (
        sse_comment("keepalive")
        + sse_encode("delta", {"seq": 1, "text": "ação – 日本 ✓"})
        + sse_encode("done", {"finish_reason": "stop"})
    )
    events = list(iter_sse(wire.split("\n")))
    assert events == [
        ("delta", {"seq": 1, "text": "ação – 日本 ✓"}),
        ("done", {"finish_reason": "stop"}),
    ]


def test_sse_event_without_blank_line_is_not_emitted():
    lines = ["event: delta", 'data: {"seq":1,"text":"x"}']
    assert list(iter_sse(lines)) == []


def test_generate_request_rejects_client_overrides():
    with pytest.raises(ValidationError):
        GenerateRequest.model_validate({"domain": "redes", "input": "oi", "system": "ignore"})
    with pytest.raises(ValidationError):
        GenerateRequest.model_validate({"domain": "redes", "input": "oi", "model": "outro"})
    with pytest.raises(ValidationError):
        GenerateRequest.model_validate({"domain": "redes", "input": ""})


def test_schema_forbids_additional_properties_and_requires_all_fields():
    schema = json_schema_for("prontuario-v1")
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"])


VALID = {
    "idade": None,
    "sexo": None,
    "queixa_principal": None,
    "diagnosticos": [],
    "medicamentos": [],
    "alergias": None,
    "sinais_vitais": {"pa": None, "fc": None, "temp_c": None, "spo2": None},
}


def test_validate_accepts_complete_output_and_keeps_unknown_as_null():
    data = validate_output("prontuario-v1", json.dumps(VALID))
    assert data["alergias"] is None
    assert data["idade"] is None


@pytest.mark.parametrize(
    "text",
    [
        "",
        "{",
        "[]",
        "{}",
        json.dumps({**VALID, "idade": 200}),
        json.dumps({**VALID, "sexo": "outro"}),
        json.dumps({**VALID, "campo_extra": 1}),
        json.dumps({**VALID, "sinais_vitais": {"pa": "120x80"}}),
    ],
)
def test_validate_rejects_invalid_or_truncated_output(text):
    with pytest.raises(ValueError):
        validate_output("prontuario-v1", text)
