# workflows/src/workflows/registry/common.py


from hera.workflows import Workflow

from workflows.config import InfraConfig
from workflows.resources.retry import IO_RETRY_STRATEGY
from workflows.templates import TemplateFactory

ITEM_PARAM = "{{item}}"
SERVICE_ACCOUNT_NAME = "argo-workflow"

ENTRYPOINT_DAG = "main-dag"

SHARD_FOLDER_PREFIX = "shard_id="
SOURCE_PARAM = "{{inputs.parameters.source}}"
SHARD_SUFFIX = ".parquet"
SHARD_PREFIX = "shard_"


def shard_path(prefix: str) -> str:
    return f"{prefix}/shard_id={ITEM_PARAM}"


def shard_ids(num_shards: int) -> list[int]:
    return list(range(num_shards))


def get_template_factory(infra_config: InfraConfig) -> TemplateFactory:
    return TemplateFactory.from_config(infra_config, retry_strategy=IO_RETRY_STRATEGY)


def new_workflow(name_prefix: str, suffix: str) -> Workflow:
    return Workflow(
        generate_name=f"{name_prefix}-{suffix}-",
        entrypoint=ENTRYPOINT_DAG,
        service_account_name=SERVICE_ACCOUNT_NAME,
    )
