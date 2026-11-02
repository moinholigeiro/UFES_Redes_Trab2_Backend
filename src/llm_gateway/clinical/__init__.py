"""Extração estruturada de prontuários (domínio `prontuario`)."""

from .schema import SCHEMAS, ProntuarioV1, json_schema_for, validate_output

__all__ = ["SCHEMAS", "ProntuarioV1", "json_schema_for", "validate_output"]
