# workflows/src/workflows/registry/candidates/common.py

from hera.workflows import Workflow

from workflows.config import InfraConfig
from workflows.config.infrastructure import ImageName
from workflows.registry.common import SERVICE_ACCOUNT_NAME
from workflows.resources.retry import IO_RETRY_STRATEGY
from workflows.templates import TemplateFactory

ENTRYPOINT_DAG = "main-dag"


def candidates_template_factory(infra_config: InfraConfig) -> TemplateFactory:
    return TemplateFactory.from_config(
        infra_config, ImageName.CANDIDATES, retry_strategy=IO_RETRY_STRATEGY
    )


def new_candidates_workflow(name_prefix: str, suffix: str) -> Workflow:
    return Workflow(
        generate_name=f"{name_prefix}-{suffix}-",
        entrypoint=ENTRYPOINT_DAG,
        service_account_name=SERVICE_ACCOUNT_NAME,
    )
