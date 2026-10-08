# workflows/src/workflows/register/candidates/common.py

WORKFLOW_NAME_PARAM = "{{workflow.name}}"
ITEM_PARAM = "{{item}}"


def _shard_path(prefix: str) -> str:
    return f"{prefix}/shard_id={ITEM_PARAM}"


def _shard_ids(num_shards: int) -> list[int]:
    return list(range(num_shards))
