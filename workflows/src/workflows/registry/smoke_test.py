# workflows/src/workflows/pipelines/__init__.py

import os

from hera.workflows import DAG, Workflow, script

from workflows.utils import LYNCEUS_VOLUME


@script(volumes=[LYNCEUS_VOLUME])
def echo(message: str, mount_path: str = ""):
    print(message)

    if mount_path:
        test_file = os.path.join(mount_path, "hera_smoke_test.txt")
        with open(test_file, "w") as f:
            f.write(f"Latest message: {message}\n")


def build_smoke_test_workflow() -> Workflow:
    """Builds and returns the smoke test workflow."""
    with Workflow(
        generate_name="hera-example-",
        entrypoint="main-dag",
        service_account_name="argo-workflow",
    ) as w:
        with DAG(name="main-dag"):
            task_a = echo(
                name="task-a",
                arguments={
                    "message": "Starting the workflow...",
                    "mount_path": LYNCEUS_VOLUME.mount_path,
                },
            )
            task_b = echo(name="task-b", arguments={"message": "Workflow complete!"})

            task_a >> task_b  # type: ignore
    return w
