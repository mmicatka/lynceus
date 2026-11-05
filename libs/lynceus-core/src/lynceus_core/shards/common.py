# libs/lynceus_core/utils/common.py


import blake3

SHARD_HASH_SCHEME = "blake3-le64"
SHARD_HASH_BYTES = 8


def get_shard_id(identifier: str, num_shards: int) -> int:
    if num_shards < 1:
        raise ValueError(f"num_shards must be >= 1, got {num_shards}")
    digest = blake3.blake3(identifier.encode("utf-8")).digest(length=SHARD_HASH_BYTES)
    return int.from_bytes(digest, "little") % num_shards
