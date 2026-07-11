# libs/protein-conformational-ensemble/src/pce/schema.py

from __future__ import annotations

import functools
import json
from importlib import resources
from typing import Any

import jsonschema

from pce.errors import SchemaValidationError


@functools.lru_cache(maxsize=1)
def load_manifest_schema() -> dict[str, Any]:
    schema_text = (
        resources.files("pce.schemas")
        .joinpath("manifest.schema.json")
        .read_text(encoding="utf-8")
    )
    result: dict[str, Any] = json.loads(schema_text)
    return result


def validate_schema(data: dict[str, Any]) -> None:
    schema = load_manifest_schema()
    validator_cls = jsonschema.validators.validator_for(schema)
    validator_cls.check_schema(schema)
    validator = validator_cls(schema)

    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.path))
    if errors:
        details = "\n".join(f"  - {_format_error(e)}" for e in errors)
        msg = f"Manifest failed schema validation ({len(errors)} error(s)):\n{details}"
        raise SchemaValidationError(msg)


def _format_error(error: jsonschema.exceptions.ValidationError) -> str:
    location = "/".join(str(p) for p in error.path) or "<root>"
    return f"{location}: {error.message}"
