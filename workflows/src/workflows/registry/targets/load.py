# workflows/src/workflows/registry/target/load.py


import re

from hera.workflows import DAG

from workflows.config.core import WorkflowConfigs
from workflows.config.templates import TemplateName
from workflows.templates import download_pdbs_template
from workflows.templates.builders import TemplateFactory
from workflows.templates.targets import generate_manifest_template

LOAD_TARGETS_DAG = "load-targets"


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _task_name(stage: str, ensemble_id: str) -> str:
    return f"{stage}-{_slug(ensemble_id)}"


def build_load_targets_dag(
    templates: TemplateFactory,
    configs: WorkflowConfigs,
) -> DAG:
    paths = configs.paths
    targets = configs.screen.targets

    download_pdbs = templates.build(TemplateName.DOWNLOAD_PDBS, download_pdbs_template)
    generate_manifest = templates.build(
        TemplateName.GENERATE_PROTEIN_ENSEMBLE_MANIFEST, generate_manifest_template
    )

    with DAG(name=LOAD_TARGETS_DAG) as load_targets_dag:
        for ensemble in targets.ensembles:
            pdbs_prefix = paths.target_pdbs(ensemble.id)

            download = download_pdbs(
                name=_task_name("download-pdbs", ensemble.id),
                arguments={
                    "pdb_ids": ",".join(member.pdb_id for member in ensemble.members),
                    "base_path": paths.mount_path,
                    "output_prefix": pdbs_prefix,
                },
            )

            manifest = generate_manifest(
                name=_task_name("generate-manifest", ensemble.id),
                arguments={
                    "base_path": paths.mount_path,
                    "input_path": pdbs_prefix,
                    "output_path": paths.target_structures(ensemble.id),
                    "ensemble_id": ensemble.id,
                    "structure_glob": "*",
                },
            )

            download >> manifest  # type: ignore

    return load_targets_dag
