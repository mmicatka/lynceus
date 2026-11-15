# workflows/src/workflows/registry/common/__init__.py


import json
from typing import Any

from hera.workflows import Task

MANIFEST_OUTPUT = "manifest"
MANIFEST_PATH = "/tmp/manifest.json"

MATCHES_OUTPUT = "matches"
MATCHES_PATH = "/tmp/manifest_matches.txt"


def json_arg(value: dict[str, Any]) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def when_unmatched(check_task: Task) -> str:
    result = f"tasks.{check_task.name}.outputs.parameters.{MATCHES_OUTPUT}"
    return f"{{{{{result}}}}} == false"
