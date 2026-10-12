# workflows/src/workflows/registry/target/load.py

from hera.workflows import DAG

from workflows.config import InfraConfig, ScreenConfig
from workflows.config.infrastructure import TemplateName
from workflows.templates import (
    TemplateFactory,
    download_pdbs_template,
)

DOWNLOAD_PDBS_DAG = "download-pdbs-dag"


def build_load_targets_dag(
    templates: TemplateFactory,
    infra_config: InfraConfig,
    screen_config: ScreenConfig,
) -> DAG:
    base_path = infra_config.volume.mount_path
    output_prefix = infra_config.storage.prefixes.target.pdbs
    pdb_ids = [
        member.pdb_id
        for ensemble in screen_config.targets.ensembles
        for member in ensemble.members
    ]
    pdb_ids_str = ",".join(pdb_ids)

    download_pdbs = templates.build(TemplateName.DOWNLOAD_PDBS, download_pdbs_template)

    with DAG(name=DOWNLOAD_PDBS_DAG) as download_dag:
        download_pdbs(
            name="download-pdbs",
            arguments={
                "pdb_ids": pdb_ids_str,
                "base_path": base_path,
                "output_prefix": output_prefix,
            },
        )

    return download_dag
