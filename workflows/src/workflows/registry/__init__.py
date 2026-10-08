# workflows/src/workflows/registry/__init__.py

from typing import Callable

from hera.workflows import Workflow

from workflows.config import InfraConfig, ScreenConfig
from workflows.registry.smoke_test import build_smoke_test_workflow
from workflows.src.workflows.registry.candidates.load import (
    build_load_candidates_workflow,
)

WorkflowBuilder = Callable[[InfraConfig, ScreenConfig], Workflow]

WORKFLOW_REGISTRY: dict[str, WorkflowBuilder] = {
    "echo": build_smoke_test_workflow,
    "load-candidates-workflow": build_load_candidates_workflow,
}

__all__ = ["WORKFLOW_REGISTRY"]
