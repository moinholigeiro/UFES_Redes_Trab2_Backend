"""Contrato de extração de prontuário (schema v1).

Metadados (id, fonte, modelo, versão) são montados pelo gateway, não pelo LLM.
Campos ausentes na fonte devem ser null; `alergias: null` significa desconhecido.
"""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, ValidationError


class Medicamento(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nome: str | None
    dose: str | None
    via: str | None
    frequencia: str | None


class SinaisVitais(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pa: str | None
    fc: str | None
    temp_c: str | None
    spo2: str | None


class ProntuarioV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    idade: StrictInt | None = Field(ge=0, le=130)
    sexo: Literal["masculino", "feminino"] | None
    queixa_principal: str | None
    diagnosticos: list[str]
    medicamentos: list[Medicamento]
    alergias: list[str] | None
    sinais_vitais: SinaisVitais


SCHEMAS: dict[str, type[BaseModel]] = {"prontuario-v1": ProntuarioV1}


def json_schema_for(name: str) -> dict[str, Any]:
    return SCHEMAS[name].model_json_schema()


def validate_output(name: str, text: str) -> dict[str, Any]:
    """Valida o JSON completo gerado. Lança ValueError se não corresponder ao schema."""
    try:
        model = SCHEMAS[name].model_validate_json(text)
    except (ValidationError, json.JSONDecodeError) as err:
        raise ValueError("saída inválida para o schema") from err
    return model.model_dump(mode="json")
