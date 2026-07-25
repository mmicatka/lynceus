# libs/protein-conformational-ensemble/src/pce/canonical.py

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from typing import Any

from protein_conformational_ensemble.errors import CanonicalizationError

_INDENT = "  "  # two-space indentation
_SAFE_PLAIN_SCALAR = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.\-/:]*$")
_AMBIGUOUS_COLON = re.compile(r":(\s|$)")

# Values that would be ambiguous as plain scalars even though they match
# the character class above (e.g. they'd reparse as bool/null/int/float).
_RESERVED_WORDS = {
    "null",
    "true",
    "false",
    "yes",
    "no",
    "on",
    "off",
    "~",
}


def canonical_float_repr(value: float) -> str:
    if math.isnan(value) or math.isinf(value):
        msg = f"NaN/Infinity cannot appear in a canonicalized value, got {value!r}"
        raise CanonicalizationError(msg)

    text = repr(value)

    if "e" in text or "E" in text:
        mantissa, _, exponent = text.lower().partition("e")
        exp_value = int(exponent)
        sign = "+" if exp_value >= 0 else "-"
        if "." not in mantissa:
            mantissa = f"{mantissa}."
        text = f"{mantissa}e{sign}{abs(exp_value)}"

    if "." not in text and "e" not in text:
        text = f"{text}."

    return text


def _quote_scalar(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    escaped = escaped.replace("\n", "\\n").replace("\t", "\\t")
    return f'"{escaped}"'


def _format_string_scalar(value: str) -> str:
    if value == "":
        return '""'
    if (
        _SAFE_PLAIN_SCALAR.match(value)
        and value.lower() not in _RESERVED_WORDS
        and not _AMBIGUOUS_COLON.search(value)
    ):
        return value
    return _quote_scalar(value)


def _format_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return canonical_float_repr(value)
    if isinstance(value, str):
        return _format_string_scalar(value)
    msg = f"Cannot canonicalize scalar of type {type(value).__name__}: {value!r}"
    raise CanonicalizationError(msg)


def _is_scalar(value: Any) -> bool:
    return value is None or isinstance(value, str | bool | int | float)


def _sorted_items(mapping: Mapping[str, Any]) -> list[tuple[str, Any]]:
    return sorted(mapping.items(), key=lambda kv: kv[0])


def _render_block(value: Any, indent: int) -> list[str]:
    pad = _INDENT * indent

    if isinstance(value, Mapping):
        if not value:
            return [f"{pad}{{}}"]
        lines: list[str] = []
        for key, val in _sorted_items(value):
            key_repr = _format_string_scalar(str(key))
            if _is_scalar(val):
                lines.append(f"{pad}{key_repr}: {_format_scalar(val)}")
            elif isinstance(val, Mapping) and not val:
                lines.append(f"{pad}{key_repr}: {{}}")
            elif (
                isinstance(val, Sequence)
                and not isinstance(val, str | bytes)
                and not val
            ):
                lines.append(f"{pad}{key_repr}: []")
            else:
                lines.append(f"{pad}{key_repr}:")
                lines.extend(_render_block(val, indent + 1))
        return lines

    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        if not value:
            return [f"{pad}[]"]
        lines = []
        for item in value:
            if _is_scalar(item):
                lines.append(f"{pad}- {_format_scalar(item)}")
            elif isinstance(item, Mapping) and not item:
                lines.append(f"{pad}- {{}}")
            elif (
                isinstance(item, Sequence)
                and not isinstance(item, str | bytes)
                and not item
            ):
                lines.append(f"{pad}- []")
            elif isinstance(item, Mapping):
                item_lines = _render_block(item, indent + 1)
                child_pad = _INDENT * (indent + 1)
                rest = item_lines[0][len(child_pad) :]
                lines.append(f"{pad}- {rest}")
                lines.extend(item_lines[1:])
            else:
                msg = (
                    "canonical_serialize does not support sequences nested directly "
                    "inside other sequences (no PCE manifest field has this shape)"
                )
                raise CanonicalizationError(msg)
        return lines

    if _is_scalar(value):
        return [f"{pad}{_format_scalar(value)}"]

    msg = f"Cannot canonicalize value of type {type(value).__name__}: {value!r}"
    raise CanonicalizationError(msg)


def canonical_serialize(value: Mapping[str, Any]) -> bytes:
    lines = _render_block(value, indent=0)
    lines = [line.rstrip() for line in lines]
    text = "\n".join(lines) + "\n"
    return text.encode("utf-8")
