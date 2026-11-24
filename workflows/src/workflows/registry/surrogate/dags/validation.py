# workflows/src/workflows/registry/surrogate/dags/validation.py


from hera.workflows import DAG, Parameter

from workflows.config.core import WorkflowConfigs
from workflows.registry.common.manifest_gate import when_unmatched
from workflows.registry.surrogate.common import SampleSpec, SampleTemplates, TaskFactory
from workflows.registry.surrogate.dags.common import as_task, docking_arguments
from workflows.registry.surrogate.dags.sample import (
    SAMPLE_PARAMETERS,
    check_task,
    resolve_sample_paths,
    state_path,
    update_manifest_task,
)
from workflows.registry.surrogate.layout import SITE_PARAMETERS, SiteLayout, ref

VALIDATION_DAG = "validation-dag"
DOCKED_KEY = "docked"
IDENTITY_PARAMETERS = ("member_id", "center")


def _site_identity() -> dict[str, str]:
    return {name: ref(name) for name in IDENTITY_PARAMETERS}


def build_validation_dag(
    templates: SampleTemplates,
    configs: WorkflowConfigs,
    layout: SiteLayout,
    spec: SampleSpec,
    sample_dag: DAG,
    dock: TaskFactory,
) -> DAG:
    identity = _site_identity()

    with DAG(
        name=VALIDATION_DAG,
        inputs=[Parameter(name=name) for name in SITE_PARAMETERS],
    ) as dag:
        sample_task = as_task(
            sample_dag(
                name="sample",
                arguments={name: ref(name) for name in SAMPLE_PARAMETERS},
            ),
            "sample",
        )
        check_docked = check_task(
            templates,
            configs,
            resolve_sample_paths(configs),
            layout,
            spec,
            "check-docked",
            DOCKED_KEY,
            identity,
        )
        gate = when_unmatched(check_docked)
        dock_task = dock(
            name="dock",
            when=gate,
            arguments=docking_arguments(spec, layout),
        )
        mark_docked = update_manifest_task(
            templates,
            layout,
            spec,
            "mark-docked",
            state_path(layout, spec),
            {**identity, DOCKED_KEY: True},
            gate,
        )

        sample_task >> check_docked >> dock_task >> mark_docked  # type: ignore

    return dag
