# workflows/src/workflows/registry/candidates.py

from hera.workflows import DAG, Workflow

from workflows.config.infrastructure import InfraConfig
from workflows.config.screen import ScreenConfig
from workflows.resources.volumes import LYNCEUS_VOLUME
from workflows.templates.candidates import build_load_candidates_template


def build_candidates_workflow(
    infra_config: InfraConfig, screen_config: ScreenConfig
) -> Workflow:
    candidates = screen_config.candidates
    load_candidates = build_load_candidates_template(infra_config)

    with Workflow(
        generate_name=f"{screen_config.name}-candidates-",
        entrypoint="main-dag",
        service_account_name="argo-workflow",
    ) as w:
        with DAG(name="main-dag"):
            load_candidates(
                name="load-candidates",
                arguments={
                    "source": "{{item}}",
                    "mount_path": LYNCEUS_VOLUME.mount_path,
                    "source_prefix": candidates.source_prefix,
                    "parquet_prefix": candidates.parquet_prefix,
                },
                with_items=candidates.sources,
            )

    return w
