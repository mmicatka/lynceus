# workflows/src/workflows/registry/common.py


ITEM_PARAM = "{{item}}"
SERVICE_ACCOUNT_NAME = "argo-workflow"

SHARD_FOLDER_PREFIX = "shard_id="
SOURCE_PARAM = "{{inputs.parameters.source}}"
SHARD_SUFFIX = ".parquet"
SHARD_PREFIX = "shard_"


def shard_path(prefix: str) -> str:
    return f"{prefix}/shard_id={ITEM_PARAM}"


def shard_ids(num_shards: int) -> list[int]:
    return list(range(num_shards))
