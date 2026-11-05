# libs/lynceus-core/src/lynceus_core/manifest/hashing.py


from pathlib import Path
from typing import Union

import blake3

from lynceus_core.io.retry import DEFAULT_RETRY_POLICY, RetryPolicy, retry_call

DEFAULT_READ_SIZE = 1024 * 1024 * 16


def _hash_once(path: Union[str, Path], read_size: int) -> str:
    hasher = blake3.blake3()
    with open(path, "rb") as f:
        while chunk := f.read(read_size):
            hasher.update(chunk)
    return hasher.hexdigest()


def hash_file(
    path: Union[str, Path],
    read_size: int = DEFAULT_READ_SIZE,
    policy: RetryPolicy = DEFAULT_RETRY_POLICY,
) -> str:
    return retry_call(lambda: _hash_once(path, read_size), f"hash {path}", policy)
