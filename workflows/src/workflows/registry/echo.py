# workflows/src/workflows/pipelines/__init__.py

from hera.workflows import DAG, Workflow, script


@script()
def echo(message: str):
    print(message)


def build_echo_workflow() -> Workflow:
    """Builds and returns the echo workflow."""
    with Workflow(
        generate_name="hera-example-",
        entrypoint="main-dag",
        service_account_name="argo-workflow",
    ) as w:
        with DAG(name="main-dag"):
            task_a = echo(
                name="task-a", arguments={"message": "Starting the workflow..."}
            )
            task_b = echo(name="task-b", arguments={"message": "Workflow complete!"})

            task_a >> task_b  # type: ignore
    return w
