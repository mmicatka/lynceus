# workflows/src/workflows/registry/smoke_test.py

import os
from dataclasses import asdict, is_dataclass

from hera.workflows import DAG, Container, Workflow, script

from workflows.config.core import WorkflowConfigs
from workflows.resources import LYNCEUS_VOLUME


@script(volumes=[LYNCEUS_VOLUME])
def echo(message: str, base_path: str = ""):
    print(message)

    if base_path:
        test_file = os.path.join(base_path, "hera_smoke_test.txt")
        with open(test_file, "w") as f:
            f.write(f"Latest message:\n{message}\n")


def _dump_config(value: object) -> str:
    if hasattr(value, "model_dump_json"):
        return value.model_dump_json(indent=2)
    if is_dataclass(value) and not isinstance(value, type):
        import json

        return json.dumps(asdict(value), indent=2, default=str)
    return repr(value)


def _format_configs(configs: WorkflowConfigs) -> str:
    if hasattr(configs, "model_dump_json"):
        return (
            f"--- WORKFLOW CONFIGURATION ---\n"
            f"{configs.model_dump_json(indent=2)}\n"
            f"------------------------------"
        )

    return (
        f"--- WORKFLOW CONFIGURATION ---\n"
        f"Screen Config:\n{_dump_config(configs.screen)}\n\n"
        f"Candidates Config:\n{_dump_config(configs.candidates)}\n\n"
        f"Templates Config:\n{_dump_config(configs.templates)}\n\n"
        f"Paths:\n{_dump_config(configs.paths)}\n"
        f"------------------------------"
    )


def build_smoke_test_workflow(configs: WorkflowConfigs) -> Workflow:
    """Builds and returns the smoke test workflow."""
    mount_path = configs.paths.mount_path
    config_dump = _format_configs(configs)

    with Workflow(
        generate_name="smoke-test-",
        entrypoint="main-dag",
        service_account_name="argo-workflow",
    ) as w:
        check_permissions = Container(
            name="check-permissions",
            image="alpine",
            command=["sh", "-c", f"ls -ld {mount_path} && id"],
            volumes=[LYNCEUS_VOLUME],
        )

        with DAG(name="main-dag"):
            task_check = check_permissions()

            task_a = echo(
                name="task-a",
                arguments={
                    "message": config_dump,
                    "base_path": mount_path,
                },
            )
            task_b = echo(name="task-b", arguments={"message": "Workflow complete!"})

            task_check >> task_a >> task_b  # type: ignore
    return w
