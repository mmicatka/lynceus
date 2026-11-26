# workflows/src/workflows/registry/surrogate/sample_site.py


from collections.abc import Sequence

from hera.workflows import DAG, Parameter, Task
from hera.workflows.models import ValueFrom

from workflows.config.core import WorkflowConfigs
from workflows.config.screen import RoundConfig, SurrogateConfig
from workflows.config.templates import TemplateName
from workflows.registry.common.manifest_gate import (
    MANIFEST_OUTPUT,
    MANIFEST_PATH,
    MATCHES_OUTPUT,
    MATCHES_PATH,
)
from workflows.registry.surrogate.common import (
    SampleSpec,
    SampleTemplates,
    TaskFactory,
)
from workflows.registry.surrogate.dags import (
    SAMPLE_PARAMETERS,
    as_task,
    build_sample_dag,
)
from workflows.registry.surrogate.dags.common import docking_arguments
from workflows.registry.surrogate.dags.validation import build_validation_dag
from workflows.registry.surrogate.layout import (
    SITE_PARAMETERS,
    VALIDATION_LABEL,
    SiteLayout,
    ref,
)
from workflows.templates import (
    merge_shards_template,
    run_docking_template,
    surrogate_sample_template,
    surrogate_train_template,
    verify_manifest_template,
)
from workflows.templates.builders import TemplateFactory
from workflows.templates.common.manifest import update_manifest_template
from workflows.templates.surrogate.sample import plan_surrogate_sample_template

SURROGATE_SITE_DAG = "surrogate-site-dag"


def _build_verify_manifest(templates: TemplateFactory) -> TaskFactory:
    return templates.build(
        TemplateName.VERIFY_MANIFEST_SURROGATE,
        verify_manifest_template,
        outputs=[
            Parameter(name=MATCHES_OUTPUT, value_from=ValueFrom(path=MATCHES_PATH))
        ],
    )


def _round_label(index: int) -> str:
    return f"round_{index + 1}"


def _validation_spec(surrogate: SurrogateConfig) -> SampleSpec:
    validation = surrogate.validation
    return SampleSpec(
        label=VALIDATION_LABEL,
        seed=validation.seed,
        num_random=validation.size,
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


def _round_labels(surrogate: SurrogateConfig) -> list[str]:
    return [_round_label(index) for index in range(len(surrogate.rounds))]


def _prior_round_labels(index: int) -> list[str]:
    return [_round_label(prior) for prior in range(index)]


def _round_model_path(
    index: int, round_config: RoundConfig, layout: SiteLayout
) -> str | None:
    if round_config.top == 0:
        return None
    if index == 0:
        raise ValueError("Round 0 has no prior model, its top must be 0")
    return layout.model_path(_round_label(index - 1))


def _round_spec(
    index: int,
    round_config: RoundConfig,
    surrogate: SurrogateConfig,
    layout: SiteLayout,
) -> SampleSpec:
    exclusions = layout.features_path_list(
        [VALIDATION_LABEL, *_prior_round_labels(index)]
    )
    return SampleSpec(
        label=_round_label(index),
        seed=surrogate.random_seed + 1 + index,
        num_random=round_config.random,
        num_top=round_config.top,
        model_path=_round_model_path(index, round_config, layout),
        exclude_inputs=tuple(exclusions),
    )


def _round_specs(surrogate: SurrogateConfig, layout: SiteLayout) -> list[SampleSpec]:
    return [
        _round_spec(index, round_config, surrogate, layout)
        for index, round_config in enumerate(surrogate.rounds)
    ]


def _sample_and_dock(
    spec: SampleSpec,
    layout: SiteLayout,
    sample_dag: DAG,
    dock: TaskFactory,
) -> tuple[Task, Task]:
    sample_name = f"sample-{spec.task_suffix}"
    sample_task = as_task(
        sample_dag(
            name=sample_name,
            arguments={name: ref(name) for name in SAMPLE_PARAMETERS},
        ),
        sample_name,
    )
    dock_task = dock(
        name=f"dock-{spec.task_suffix}",
        arguments=docking_arguments(spec, layout),
    )
    sample_task >> dock_task  # type: ignore
    return sample_task, dock_task


def _train(
    spec: SampleSpec,
    layout: SiteLayout,
    surrogate_train: TaskFactory,
    training_labels: Sequence[str],
) -> Task:
    return surrogate_train(
        name=f"train-{spec.task_suffix}",
        arguments=_train_arguments(spec, layout, training_labels),
    )


def _build_sample_templates(templates: TemplateFactory) -> SampleTemplates:
    return SampleTemplates(
        sample=templates.build(
            TemplateName.SURROGATE_SAMPLE_BY_PREDICTION,
            surrogate_sample_template,
        ),
        merge_shards=templates.build(TemplateName.MERGE_SHARDS, merge_shards_template),
        plan=templates.build(
            TemplateName.PLAN_SURROGATE_SAMPLE,
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
            TemplateName.UPDATE_MANIFEST_SURROGATE, update_manifest_template
        ),
    )


def build_surrogate_site_dag(
    templates: TemplateFactory,
    configs: WorkflowConfigs,
) -> DAG:
    surrogate = configs.screen.filter.surrogate
    layout = SiteLayout(paths=configs.paths)
    validation_spec = _validation_spec(surrogate)
    round_specs = _round_specs(surrogate, layout)

    dock = templates.build(TemplateName.RUN_DOCKING, run_docking_template)
    surrogate_train = templates.build(
        TemplateName.SURROGATE_TRAIN, surrogate_train_template
    )
    sample_templates = _build_sample_templates(templates)

    sample_dags = {
        spec.label: build_sample_dag(sample_templates, configs, layout, spec)
        for spec in round_specs
    }
    validation_dag = build_validation_dag(
        sample_templates,
        configs,
        layout,
        validation_spec,
        build_sample_dag(sample_templates, configs, layout, validation_spec),
        dock,
    )

    with DAG(
        name=SURROGATE_SITE_DAG,
        inputs=[Parameter(name=name) for name in SITE_PARAMETERS],
    ) as site_dag:
        round_labels = _round_labels(surrogate)
        previous_task = as_task(
            validation_dag(
                name="validation",
                arguments={name: ref(name) for name in SITE_PARAMETERS},
            ),
            "validation",
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
