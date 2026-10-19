# workflows/src/workflows/registry/core.py

from typing import Callable

from hera.workflows import Workflow

from workflows.config import InfraConfig, ScreenConfig
from workflows.registry.candidates import (
    build_candidates_workflow,
    build_load_candidates_workflow,
)
from workflows.registry.smoke_test import build_smoke_test_workflow
from workflows.registry.surrogate import build_surrogate_sample_workflow
from workflows.registry.targets import build_targets_workflow

WorkflowBuilder = Callable[[InfraConfig, ScreenConfig], Workflow]

WORKFLOW_REGISTRY: dict[str, WorkflowBuilder] = {
    "echo": build_smoke_test_workflow,
    "load-candidates-workflow": build_load_candidates_workflow,
    "candidates-workflow": build_candidates_workflow,
    "targets-workflow": build_targets_workflow,
    "surrogate-workflow": build_surrogate_sample_workflow,
}
