# workflows/src/workflows/registry/surrogate/sample_site.py


from typing import Sequence

from hera.workflows import DAG, Parameter, Task
from hera.workflows.models import ValueFrom

from workflows.config import InfraConfig, ScreenConfig
from workflows.config.infrastructure import ComputeTemplateName
from workflows.config.screen import RoundConfig, SurrogateConfig
from workflows.registry.common.manifest_gate import (
    MANIFEST_OUTPUT,
    MANIFEST_PATH,
    MATCHES_OUTPUT,
    MATCHES_PATH,
)
from workflows.registry.surrogate.common import (
    PredictionSampleSpec,
    RandomSampleSpec,
    SampleTemplates,
)
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
from workflows.templates import (
    TemplateFactory,
    merge_shards_template,
    run_docking_template,
    surrogate_sample_by_prediction_template,
    surrogate_sample_template,
    surrogate_train_template,
    verify_manifest_template,
)
from workflows.templates.common.update_manifest import update_manifest_template
from workflows.templates.surrogate.sample import plan_surrogate_sample_template

SURROGATE_SITE_DAG = "surrogate-site-dag"


STAGING_GLOB = "*.parquet"
INPUT_PATH_KEY = "input_path"


def _build_verify_manifest(templates: TemplateFactory):
    return templates.build(
        ComputeTemplateName.VERIFY_MANIFEST_SURROGATE,
        verify_manifest_template,
        outputs=[
            Parameter(name=MATCHES_OUTPUT, value_from=ValueFrom(path=MATCHES_PATH))
        ],
    )


def _docking_arguments(spec: SampleSpec, layout: SiteLayout) -> dict:
    return {
        "base_path": layout.base_path,
        "ensemble": layout.ensemble_path,
        "member_id": ref("member_id"),
        "ligands_path": layout.docking_input_path(spec.label),
        "center": ref("center"),
        "site_id": ref("site_id"),
        "output_path": layout.label_dir(spec.label),
    }


def _round_label(index: int) -> str:
    return f"round_{index}"


def _round_labels(surrogate: SurrogateConfig) -> list[str]:
    return [_round_label(index) for index in range(len(surrogate.rounds))]


def _validation_spec(surrogate: SurrogateConfig) -> SampleSpec:
    return RandomSampleSpec(
        label=VALIDATION_LABEL,
        seed=surrogate.seed,
        num_samples=surrogate.validation,
    )


def _train_arguments(
    spec: SampleSpec, layout: SiteLayout, training_labels: Sequence[str]
) -> dict:
    return {
        "base_path": layout.base_path,
        "train_features": layout.features_paths(training_labels),
        "train_labels": layout.labels_paths(training_labels),
        "validation_features": layout.features_path(VALIDATION_LABEL),
        "validation_labels": layout.docking_results_path(VALIDATION_LABEL),
        "model_path": layout.model_path(spec.label),
    }


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


def _train(
    spec: SampleSpec,
    layout: SiteLayout,
    surrogate_train,
    training_labels: Sequence[str],
) -> Task:
    return surrogate_train(
        name=f"train-{spec.task_suffix}",
        arguments=_train_arguments(spec, layout, training_labels),
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
    round_specs = _round_specs(surrogate, layout)

    dock = templates.build(ComputeTemplateName.RUN_DOCKING, run_docking_template)
    surrogate_train = templates.build(
        ComputeTemplateName.SURROGATE_TRAIN, surrogate_train_template
    )
    sample_templates = SampleTemplates(
        sample={
            RandomSampleSpec: templates.build(
                ComputeTemplateName.SURROGATE_SAMPLE, surrogate_sample_template
            ),
            PredictionSampleSpec: templates.build(
                ComputeTemplateName.SURROGATE_SAMPLE_BY_PREDICTION,
                surrogate_sample_by_prediction_template,
            ),
        },
        merge_shards=templates.build(
            ComputeTemplateName.MERGE_SHARDS, merge_shards_template
        ),
        plan=templates.build(
            ComputeTemplateName.PLAN_SURROGATE_SAMPLE,
            plan_surrogate_sample_template,
            outputs=[
                Parameter(
                    name=MANIFEST_OUTPUT,
                    value_from=ValueFrom(path=MANIFEST_PATH),
                )
            ],
        ),
        verify_manifest=_build_verify_manifest(templates),
        update_manifest=templates.build(
            ComputeTemplateName.UPDATE_MANIFEST_SURROGATE, update_manifest_template
        ),
    )

    sample_dags = {
        spec.label: build_sample_dag(sample_templates, infra_config, layout, spec)
        for spec in [validation_spec, *round_specs]
    }

    with DAG(
        name=SURROGATE_SITE_DAG,
        inputs=[Parameter(name=name) for name in SITE_PARAMETERS],
    ) as site_dag:
        round_labels = _round_labels(surrogate)
        _, previous_task = _sample_and_dock(
            validation_spec,
            layout,
            sample_dags[validation_spec.label],
            dock,
        )

        for index, spec in enumerate(round_specs):
            sample_task, dock_task = _sample_and_dock(
                spec,
                layout,
                sample_dags[spec.label],
                dock,
            )
            train_task = _train(
                spec, layout, surrogate_train, round_labels[: index + 1]
            )

            previous_task >> sample_task  # type: ignore
            dock_task >> train_task  # type: ignore
            previous_task = train_task

    return site_dag
