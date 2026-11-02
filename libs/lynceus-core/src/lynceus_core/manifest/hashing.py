# libs/lynceus-core/src/lynceus_core/manifest/hashing.py

from pathlib import Path
from typing import Union

import blake3

DEFAULT_READ_SIZE = 1024 * 1024


def hash_file(path: Union[str, Path], read_size: int = DEFAULT_READ_SIZE) -> str:
    hasher = blake3.blake3()
    with open(path, "rb") as f:
        while chunk := f.read(read_size):
            hasher.update(chunk)
    return hasher.hexdigest()
