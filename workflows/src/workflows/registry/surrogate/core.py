# workflows/src/workflows/registry/surrogate/core.py

from hera.workflows import DAG, Parameter

from workflows.config import InfraConfig, ScreenConfig
from workflows.config.infrastructure import TemplateName
from workflows.config.screen import SurrogateConfig
from workflows.registry.surrogate.layout import (
    SITE_PARAMETERS,
    VALIDATION_LABEL,
    SiteLayout,
    ref,
)
from workflows.registry.surrogate.sample_site import (
    SAMPLE_PARAMETERS,
    SampleSpec,
    build_sample_dag,
)
from workflows.templates.builders import TemplateFactory
from workflows.templates.docking.run_docking import run_docking_template

SURROGATE_SITE_DAG = "surrogate-site-dag"


def _sample_specs(surrogate: SurrogateConfig) -> list[SampleSpec]:
    rounds = [
        SampleSpec(f"round_{index}", round_config.uniform, surrogate.seed + 1 + index)
        for index, round_config in enumerate(surrogate.rounds)
    ]
    return [SampleSpec(VALIDATION_LABEL, surrogate.validation, surrogate.seed), *rounds]


def _docking_arguments(spec: SampleSpec, layout: SiteLayout) -> dict:
    return {
        "ensemble": layout.ensemble_path,
        "member_id": ref("member_id"),
        "ligands_path": layout.docking_input_path(spec.label),
        "center": ref("center"),
        "site_id": ref("site_id"),
        "out_parquet": layout.docking_results_path(spec.label),
    }


def build_surrogate_site_dag(
    templates: TemplateFactory,
    infra_config: InfraConfig,
    screen_config: ScreenConfig,
) -> DAG:
    layout = SiteLayout(
        base_path=infra_config.volume.mount_path,
        surrogate_prefix=infra_config.storage.prefixes.surrogate.ensembles,
        target_prefix=infra_config.storage.prefixes.target.ensembles,
    )
    specs = _sample_specs(screen_config.filter.surrogate)

    dock = templates.build(TemplateName.RUN_DOCKING, run_docking_template)
    sample_dags = {
        spec.label: build_sample_dag(templates, infra_config, layout, spec)
        for spec in specs
    }

    with DAG(
        name=SURROGATE_SITE_DAG,
        inputs=[Parameter(name=name) for name in SITE_PARAMETERS],
    ) as site_dag:
        for spec in specs:
            sample_task = sample_dags[spec.label](
                name=f"sample-{spec.task_suffix}",
                arguments={name: ref(name) for name in SAMPLE_PARAMETERS},
            )
            dock_task = dock(
                name=f"dock-{spec.task_suffix}",
                arguments=_docking_arguments(spec, layout),
            )
            sample_task >> dock_task  # type: ignore

    return site_dag
