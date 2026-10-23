# workflows/src/workflows/registry/surrogate/sample_site.py

from hera.workflows import DAG, Parameter, Task

from workflows.config import InfraConfig, ScreenConfig
from workflows.config.infrastructure import TemplateName
from workflows.config.screen import RoundConfig, SurrogateConfig
from workflows.registry.surrogate.layout import (
    SITE_PARAMETERS,
    VALIDATION_LABEL,
    SiteLayout,
    ref,
)
from workflows.registry.surrogate.sample import (
    SAMPLE_PARAMETERS,
    PredictionSampleSpec,
    RandomSampleSpec,
    SampleSpec,
    build_sample_dag,
)
from workflows.templates import (
    TemplateFactory,
    merge_shards_template,
    run_docking_template,
    surrogate_prepare_validation_template,
    surrogate_sample_by_prediction_template,
    surrogate_sample_template,
    surrogate_train_template,
)

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


def _prepare_validation_arguments(
    layout: SiteLayout, surrogate: SurrogateConfig
) -> dict:
    return {
        "validation_path": layout.docking_results_path(VALIDATION_LABEL),
        "active_percentile": surrogate.active_percentile,
    }


def _train_arguments(spec: SampleSpec, layout: SiteLayout, threshold: str) -> dict:
    return {
        "train_features": layout.features_path(spec.label),
        "train_labels": layout.labels_path(spec.label),
        "validation_features": layout.features_path(VALIDATION_LABEL),
        "validation_labels": layout.docking_results_path(VALIDATION_LABEL),
        "model_path": layout.model_path(spec.label),
        "threshold": threshold,
    }


def _round_label(index: int) -> str:
    return f"round_{index}"


def _validation_spec(surrogate: SurrogateConfig) -> SampleSpec:
    return RandomSampleSpec(
        label=VALIDATION_LABEL,
        seed=surrogate.seed,
        num_samples=surrogate.validation,
    )


def _round_spec(
    index: int,
    round_config: RoundConfig,
    surrogate: SurrogateConfig,
    layout: SiteLayout,
) -> SampleSpec:
    seed = surrogate.seed + 1 + index
    if index == 0:
        return RandomSampleSpec(
            label=_round_label(index),
            seed=seed,
            num_samples=round_config.random,
        )
    return PredictionSampleSpec(
        label=_round_label(index),
        seed=seed,
        model_path=layout.model_path(_round_label(index - 1)),
        num_top=round_config.top,
        num_random=round_config.random,
    )


def _round_specs(surrogate: SurrogateConfig, layout: SiteLayout) -> list[SampleSpec]:
    return [
        _round_spec(index, round_config, surrogate, layout)
        for index, round_config in enumerate(surrogate.rounds)
    ]


def _sample_and_dock(
    spec: SampleSpec,
    layout: SiteLayout,
    sample_dag,
    dock,
) -> tuple[Task, Task]:
    sample_task = sample_dag(
        name=f"sample-{spec.task_suffix}",
        arguments={name: ref(name) for name in SAMPLE_PARAMETERS},
    )
    dock_task = dock(
        name=f"dock-{spec.task_suffix}",
        arguments=_docking_arguments(spec, layout),
    )
    sample_task >> dock_task  # type: ignore
    return sample_task, dock_task


def _prepare_validation(
    layout: SiteLayout,
    surrogate: SurrogateConfig,
    validation_dock_task: Task,
    prepare_validation,
) -> Task:
    prepare_task = prepare_validation(
        name="prepare-validation",
        arguments=_prepare_validation_arguments(layout, surrogate),
    )
    validation_dock_task >> prepare_task  # type: ignore
    return prepare_task


def _train(
    spec: SampleSpec,
    layout: SiteLayout,
    surrogate_train,
    prepare_task: Task,
) -> Task:
    train_task = surrogate_train(
        name=f"train-{spec.task_suffix}",
        arguments=_train_arguments(spec, layout, prepare_task.result),
    )
    prepare_task >> train_task  # type: ignore
    return train_task


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
    round_specs = _round_specs(surrogate, layout)

    dock = templates.build(TemplateName.RUN_DOCKING, run_docking_template)
    merge_shards = templates.build(TemplateName.MERGE_SHARDS, merge_shards_template)
    prepare_validation = templates.build(
        TemplateName.SURROGATE_PREPARE_VALIDATION,
        surrogate_prepare_validation_template,
    )
    surrogate_train = templates.build(
        TemplateName.SURROGATE_TRAIN, surrogate_train_template
    )
    sample_templates = {
        RandomSampleSpec: templates.build(
            TemplateName.SURROGATE_SAMPLE, surrogate_sample_template
        ),
        PredictionSampleSpec: templates.build(
            TemplateName.SURROGATE_SAMPLE_BY_PREDICTION,
            surrogate_sample_by_prediction_template,
        ),
    }

    sample_dags = {
        spec.label: build_sample_dag(
            sample_templates[type(spec)], merge_shards, infra_config, layout, spec
        )
        for spec in [validation_spec, *round_specs]
    }

    with DAG(
        name=SURROGATE_SITE_DAG,
        inputs=[Parameter(name=name) for name in SITE_PARAMETERS],
    ) as site_dag:
        _, previous_task = _sample_and_dock(
            validation_spec, layout, sample_dags[validation_spec.label], dock
        )
        prepare_task = _prepare_validation(
            layout, surrogate, previous_task, prepare_validation
        )

        for spec in round_specs:
            sample_task, dock_task = _sample_and_dock(
                spec, layout, sample_dags[spec.label], dock
            )
            train_task = _train(spec, layout, surrogate_train, prepare_task)

            previous_task >> sample_task  # type: ignore
            dock_task >> train_task  # type: ignore
            previous_task = train_task

    return site_dag
