# libs/lynceus-core/src/lynceus_core/io/batching.py

from collections.abc import Sequence
from pathlib import Path


def plan_batches(files: Sequence[Path], max_bytes: int) -> list[list[Path]]:
    batches: list[list[Path]] = []
    current: list[Path] = []
    current_bytes = 0
    for path in files:
        size = path.stat().st_size
        if size > max_bytes:
            raise RuntimeError(
                f"{path} is {size} bytes, larger than the batch cap of {max_bytes}"
            )
        if current and current_bytes + size > max_bytes:
            batches.append(current)
            current = []
            current_bytes = 0
        current.append(path)
        current_bytes += size
    if current:
        batches.append(current)
    return batches
