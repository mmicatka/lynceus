# workflows/src/workflows/registry/surrogate/sample_site.py

from hera.workflows import DAG, Parameter, Task

from workflows.config import InfraConfig, ScreenConfig
from workflows.config.infrastructure import TemplateName
from workflows.config.screen import SurrogateConfig
from workflows.registry.surrogate.layout import (
    SITE_PARAMETERS,
    VALIDATION_LABEL,
    SiteLayout,
    ref,
)
from workflows.registry.surrogate.sample import (
    SAMPLE_PARAMETERS,
    SampleSpec,
    build_sample_dag,
)
from workflows.templates import merge_shards_template, surrogate_sample_template
from workflows.templates.builders import TemplateFactory
from workflows.templates.docking.run_docking import run_docking_template
from workflows.templates.surrogate.surrogate_train import surrogate_train_template

SURROGATE_SITE_DAG = "surrogate-site-dag"


def _docking_arguments(spec: SampleSpec, layout: SiteLayout) -> dict:
    return {
        "ensemble": layout.ensemble_path,
        "member_id": ref("member_id"),
        "ligands_path": layout.docking_input_path(spec.label),
        "center": ref("center"),
        "site_id": ref("site_id"),
        "out_parquet": layout.docking_results_path(spec.label),
    }


def _train_arguments(spec: SampleSpec, layout: SiteLayout) -> dict:
    return {
        "train_features": layout.features_path(spec.label),
        "train_labels": layout.labels_path(spec.label),
        "validation_features": layout.features_path(VALIDATION_LABEL),
        "validation_labels": layout.docking_results_path(VALIDATION_LABEL),
        "model_path": layout.model_path(spec.label),
    }


def _validation_spec(surrogate: SurrogateConfig) -> SampleSpec:
    return SampleSpec(VALIDATION_LABEL, surrogate.validation, surrogate.seed)


def _round_specs(surrogate: SurrogateConfig) -> list[SampleSpec]:
    return [
        SampleSpec(f"round_{index}", round_config.uniform, surrogate.seed + 1 + index)
        for index, round_config in enumerate(surrogate.rounds)
    ]


def _sample_and_dock(
    spec: SampleSpec,
    layout: SiteLayout,
    sample_dags: dict,
    dock,
) -> tuple[Task, Task]:
    sample_task = sample_dags[spec.label](
        name=f"sample-{spec.task_suffix}",
        arguments={name: ref(name) for name in SAMPLE_PARAMETERS},
    )
    dock_task = dock(
        name=f"dock-{spec.task_suffix}",
        arguments=_docking_arguments(spec, layout),
    )
    sample_task >> dock_task  # type: ignore
    return sample_task, dock_task


def _train(spec: SampleSpec, layout: SiteLayout, surrogate_train) -> Task:
    return surrogate_train(
        name=f"train-{spec.task_suffix}",
        arguments=_train_arguments(spec, layout),
    )


def build_surrogate_site_dag(
    templates: TemplateFactory,
    infra_config: InfraConfig,
    screen_config: ScreenConfig,
) -> DAG:
    layout = SiteLayout(
        base_path=infra_config.volume.mount_path,
        surrogate_prefix=infra_config.storage.prefixes.surrogate.root,
        target_prefix=infra_config.storage.prefixes.target.ensembles,
        screen_name=screen_config.name,
    )

    surrogate = screen_config.filter.surrogate
    validation_spec = _validation_spec(surrogate)
    round_specs = _round_specs(surrogate)

    dock = templates.build(TemplateName.RUN_DOCKING, run_docking_template)
    surrogate_sample = templates.build(
        TemplateName.SURROGATE_SAMPLE, surrogate_sample_template
    )
    merge_shards = templates.build(TemplateName.MERGE_SHARDS, merge_shards_template)
    surrogate_train = templates.build(
        TemplateName.SURROGATE_TRAIN, surrogate_train_template
    )

    sample_dags = {
        spec.label: build_sample_dag(
            surrogate_sample, merge_shards, infra_config, layout, spec
        )
        for spec in [validation_spec, *round_specs]
    }

    with DAG(
        name=SURROGATE_SITE_DAG,
        inputs=[Parameter(name=name) for name in SITE_PARAMETERS],
    ) as site_dag:
        _, previous = _sample_and_dock(validation_spec, layout, sample_dags, dock)

        for spec in round_specs:
            sample_task, dock_task = _sample_and_dock(spec, layout, sample_dags, dock)
            train_task = _train(spec, layout, surrogate_train)

            previous >> sample_task  # type: ignore
            dock_task >> train_task  # type: ignore
            previous = train_task

    return site_dag
