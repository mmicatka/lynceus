# workflows/src/workflows/registry/__init__.py


from workflows.registry.smoke_test import build_smoke_test_workflow

WORKFLOW_REGISTRY = {
    "echo": build_smoke_test_workflow,
    # "data-pipeline": build_data_pipeline_workflow,
}

__all__ = ["WORKFLOW_REGISTRY"]
