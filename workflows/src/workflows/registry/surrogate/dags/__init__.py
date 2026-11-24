# workflows/src/workflows/registry/surrogate/dags/__init__.py


from .common import as_task, docking_arguments
from .sample import SAMPLE_PARAMETERS, build_sample_dag
from .validation import build_validation_dag

__all__ = [
    "as_task",
    "docking_arguments",
    "build_sample_dag",
    "build_validation_dag",
    "SAMPLE_PARAMETERS",
]
