# workflows/src/workflows/registry/surrogate/dags/common.py


from hera.workflows import Step, Task

from workflows.registry.surrogate.common import SampleSpec
from workflows.registry.surrogate.layout import SiteLayout, ref


def as_task(created: Step | Task | None, name: str) -> Task:
    if not isinstance(created, Task):
        raise RuntimeError(f"Expected {name} to create a Task, got {type(created)}")
    return created


def docking_arguments(spec: SampleSpec, layout: SiteLayout) -> dict:
    return {
        "base_path": layout.base_path,
        "ensemble": layout.ensemble_path,
        "member_id": ref("member_id"),
        "ligands_path": layout.docking_input_path(spec.label),
        "center": ref("center"),
        "site_id": ref("site_id"),
        "output_path": layout.label_dir(spec.label),
    }
