# workflows/src/workflows/registry/common/core.py


from hera.workflows import Workflow

from workflows.config.templates import TemplatesConfig
from workflows.templates import TemplateFactory

ITEM_PARAM = "{{item}}"
SERVICE_ACCOUNT_NAME = "argo-workflow"

ENTRYPOINT_DAG = "main-dag"

SOURCE_INPUT_NAME = "source"
SHARD_FOLDER_PREFIX = "shard_id="
SOURCE_PARAM = "{{inputs.parameters.source}}"
SHARD_SUFFIX = ".parquet"
SHARD_PREFIX = "shard_"


def shard_ids(num_shards: int) -> list[int]:
    return list(range(num_shards))


def shard_filename(shard: str) -> str:
    return f"{SHARD_PREFIX}{shard}{SHARD_SUFFIX}"


def get_template_factory(templates_config: TemplatesConfig) -> TemplateFactory:
    return TemplateFactory.from_config(templates_config)


def new_workflow(name_prefix: str, suffix: str) -> Workflow:
    return Workflow(
        generate_name=f"{name_prefix}-{suffix}-",
        entrypoint=ENTRYPOINT_DAG,
        service_account_name=SERVICE_ACCOUNT_NAME,
    )
