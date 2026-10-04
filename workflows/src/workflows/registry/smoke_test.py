# workflows/src/workflows/pipelines/__init__.py

from hera.workflows import DAG, Parameter, Workflow, script

from workflows.utils.artifact import ArtifactSpec

WORKFLOW_NAMESPACE = "workflows"

SMOKE_MESSAGE = ArtifactSpec(
    name="smoke-message",
    path="/tmp/artifacts/smoke_message.txt",
)


@script(outputs=SMOKE_MESSAGE.output())
def write_message(message: str, output_path: str):
    from pathlib import Path

    print(message)

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"Latest message: {message}\n")


@script(inputs=SMOKE_MESSAGE.input())
def read_message(input_path: str):
    from pathlib import Path

    print(Path(input_path).read_text())


def build_smoke_test_workflow() -> Workflow:
    """Builds and returns the smoke test workflow."""
    with Workflow(
        generate_name="hera-example-",
        namespace=WORKFLOW_NAMESPACE,
        entrypoint="main-dag",
        service_account_name="argo-workflow",
    ) as w:
        with DAG(name="main-dag"):
            task_a = write_message(
                name="task-a",
                arguments={
                    "message": "Starting the workflow...",
                    "output_path": SMOKE_MESSAGE.path,
                },
            )
            task_b = read_message(
                name="task-b",
                arguments=[
                    Parameter(name="input_path", value=SMOKE_MESSAGE.path),
                    task_a.get_artifact(SMOKE_MESSAGE.name),
                ],
            )

            task_a >> task_b  # type: ignore
    return w
