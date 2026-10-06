# workflows/src/workflows/pipelines/smoke_test.py

import os

from hera.workflows import DAG, Container, Workflow, script

from workflows.config.infrastructure import InfraConfig
from workflows.config.screen import ScreenConfig
from workflows.resources import LYNCEUS_VOLUME


@script(volumes=[LYNCEUS_VOLUME])
def echo(message: str, mount_path: str = ""):
    print(message)

    if mount_path:
        test_file = os.path.join(mount_path, "hera_smoke_test.txt")
        with open(test_file, "w") as f:
            f.write(f"Latest message:\n{message}\n")


def build_smoke_test_workflow(
    infra_config: InfraConfig, screen_config: ScreenConfig
) -> Workflow:
    """Builds and returns the smoke test workflow."""

    infra_json = infra_config.model_dump_json(indent=2)
    screen_json = screen_config.model_dump_json(indent=2)

    config_dump = (
        f"--- WORKFLOW CONFIGURATION ---\n"
        f"Infra Config:\n{infra_json}\n\n"
        f"Screen Config:\n{screen_json}\n"
        f"------------------------------"
    )

    with Workflow(
        generate_name="smoke-test-",
        entrypoint="main-dag",
        service_account_name="argo-workflow",
    ) as w:
        check_permissions = Container(
            name="check-permissions",
            image="alpine",
            command=["sh", "-c", "ls -ld /mnt/data && id"],
            volumes=[LYNCEUS_VOLUME],
        )

        with DAG(name="main-dag"):
            task_check = check_permissions()

            task_a = echo(
                name="task-a",
                arguments={
                    "message": config_dump,
                    "mount_path": LYNCEUS_VOLUME.mount_path,
                },
            )
            task_b = echo(name="task-b", arguments={"message": "Workflow complete!"})

            task_check >> task_a >> task_b  # type: ignore
    return w
