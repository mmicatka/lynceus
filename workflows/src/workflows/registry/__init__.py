# workflows/src/workflows/registry/__init__.py


from typing import Callable

from hera.workflows import Workflow

from workflows.config import InfraConfig, ScreenConfig
from workflows.registry.smoke_test import build_smoke_test_workflow

WorkflowBuilder = Callable[[InfraConfig, ScreenConfig], Workflow]

WORKFLOW_REGISTRY: dict[str, WorkflowBuilder] = {
    "echo": build_smoke_test_workflow,
    # "data-pipeline": build_data_pipeline_workflow,
}

__all__ = ["WORKFLOW_REGISTRY"]
