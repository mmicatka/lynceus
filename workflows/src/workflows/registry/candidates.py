# workflows/src/workflows/registry/candidates.py

from hera.workflows import DAG, Workflow

from workflows.config.infrastructure import InfraConfig
from workflows.config.screen import ScreenConfig
from workflows.resources.volumes import LYNCEUS_VOLUME
from workflows.templates.candidates import build_load_candidates_template
from workflows.templates.candidates.generate_subset_manifest import (
    build_generate_subset_manifest_template,
)


def build_candidates_workflow(
    infra_config: InfraConfig, screen_config: ScreenConfig
) -> Workflow:
    candidates_config = screen_config.candidates
    storage_config = infra_config.storage

    load_candidates_template = build_load_candidates_template(infra_config)
    generate_subset_manifest_template = build_generate_subset_manifest_template(
        infra_config
    )

    with Workflow(
        generate_name=f"{screen_config.name}-candidates-",
        entrypoint="main-dag",
        service_account_name="argo-workflow",
    ) as w:
        with DAG(name="main-dag"):
            load_candidates_task = load_candidates_template(
                name="load-candidates",
                arguments={
                    "source": "{{item}}",
                    "mount_path": LYNCEUS_VOLUME.mount_path,
                    "source_prefix": storage_config.prefixes.candidates.raw_smiles,
                    "parquet_prefix": storage_config.prefixes.candidates.raw_parquet,
                },
                with_items=candidates_config.sources,
            )

            generate_subset_manifest_task = generate_subset_manifest_template(
                name="generate-subset-manifest",
                arguments={
                    "source_dir": f"{LYNCEUS_VOLUME.mount_path}/"
                    f"{storage_config.prefixes.candidates.raw_parquet}",
                    "target_total": candidates_config.target_total,
                    "min_per_source": candidates_config.min_per_source,
                    "output": f"{LYNCEUS_VOLUME.mount_path}/{screen_config.name}/"
                    f"{storage_config.files.subset_manifest}",
                },
            )

            load_candidates_task >> generate_subset_manifest_task  # type: ignore

    return w
