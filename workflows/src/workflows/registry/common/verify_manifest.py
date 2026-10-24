# workflows/src/workflows/registry/common/verify_manifest.py


import json

from hera.workflows import Task

MANIFEST_MATCHES_OUTPUT = "matches"


def expect_argument(expected: dict) -> str:
    return json.dumps(expected, sort_keys=True)


def run_unless_matched(check_task: Task) -> str:
    return (
        f"{{{{tasks.{check_task.name}.outputs.parameters.{MANIFEST_MATCHES_OUTPUT}}}}}"
        " != true"
    )


def verify_manifest_task(
    check_manifest, name: str, manifest_path: str, expected: dict
) -> Task:
    return check_manifest(
        name=name,
        arguments={
            "manifest_path": manifest_path,
            "expect": expect_argument(expected),
        },
    )
