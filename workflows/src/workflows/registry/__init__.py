# workflows/src/workflows/registry/__init__.py


from workflows.registry.echo import build_echo_workflow

WORKFLOW_REGISTRY = {
    "echo": build_echo_workflow,
    # "data-pipeline": build_data_pipeline_workflow,
}

__all__ = ["WORKFLOW_REGISTRY"]
