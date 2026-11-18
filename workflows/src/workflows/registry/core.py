# workflows/src/workflows/registry/core.py

from collections.abc import Callable

from hera.workflows import Workflow

from workflows.config.core import WorkflowConfigs
from workflows.registry.candidates import (
    build_load_candidates_workflow,
    build_preprocess_candidates_workflow,
    build_sample_candidates_workflow,
)
from workflows.registry.candidates.featurize import build_featurize_candidates_workflow
from workflows.registry.smoke_test import build_smoke_test_workflow
from workflows.registry.surrogate import build_surrogate_workflow
from workflows.registry.targets import build_targets_workflow

WorkflowBuilder = Callable[[WorkflowConfigs], Workflow]

WORKFLOW_REGISTRY: dict[str, WorkflowBuilder] = {
    "echo": build_smoke_test_workflow,
    "load-candidates-workflow": build_load_candidates_workflow,
    "sample-candidates-workflow": build_sample_candidates_workflow,
    "preprocess-candidates-workflow": build_preprocess_candidates_workflow,
    "featurize-candidates-workflow": build_featurize_candidates_workflow,
    "targets-workflow": build_targets_workflow,
    "surrogate-workflow": build_surrogate_workflow,
}
