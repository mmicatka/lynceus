# workflows/src/workflows/registry/target/load.py

from hera.workflows import DAG, Workflow

from workflows.config import InfraConfig, ScreenConfig
from workflows.config.infrastructure import ImageName, TemplateName
from workflows.registry.common import (
    ENTRYPOINT_DAG,
    get_template_factory,
    new_workflow,
)
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

    download_pdbs = templates.build(
        TemplateName.DOWNLOAD_PDBS, ImageName.TARGETS, download_pdbs_template
    )

    with DAG(name=DOWNLOAD_PDBS_DAG) as download_dag:
        download_pdbs(
            name="download-pdbs",
            arguments={
                "pdb_ids": pdb_ids_str,
                "mount_path": base_path,
                "output_prefix": output_prefix,
            },
        )

    return download_dag


def build_download_pdbs_workflow(
    infra_config: InfraConfig, screen_config: ScreenConfig
) -> Workflow:
    templates = get_template_factory(infra_config)

    with new_workflow(screen_config.name, "download-pdbs") as w:
        download_dag = build_load_targets_dag(templates, infra_config, screen_config)

        with DAG(name=ENTRYPOINT_DAG):
            download_dag(name="download-pdbs")

    return w
