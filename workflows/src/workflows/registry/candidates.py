# workflows/src/workflows/registry/candidates.py

from hera.workflows import DAG, Parameter, Workflow

from workflows.components import list_folders
from workflows.resources import LYNCEUS_VOLUME


def build_candidate_workflow(max_parallel: int = 50) -> Workflow:
    with Workflow(
        generate_name="candidate-",
        entrypoint="main",
        service_account_name="argo-workflow",
        parallelism=max_parallel,
        arguments=[
            Parameter(name="root", value=LYNCEUS_VOLUME.mount_path),
            Parameter(name="prefix", value=""),
        ],
    ) as w:
        with DAG(name="main"):
            discovered = list_folders(
                name="list-folders",
                arguments={
                    "root": "{{workflow.parameters.root}}",
                    "prefix": "{{workflow.parameters.prefix}}",
                },
            )
            processed = process_folder(
                name="process-folder",
                arguments={
                    "root": "{{workflow.parameters.root}}",
                    "folder": "{{item}}",
                },
                with_param=discovered.result,
            )
            discovered >> processed  # type: ignore
    return w
