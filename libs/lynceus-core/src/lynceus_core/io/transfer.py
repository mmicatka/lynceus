# libs/lynceus-core/src/lynceus_core/io/transfer.py

import shutil
import time
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from lynceus_core.logging import get_lynceus_logger

logger = get_lynceus_logger()


@dataclass(frozen=True)
class RetryPolicy:
    attempts: int = 5
    backoff_seconds: float = 0.5
    retry_on: tuple[type[OSError], ...] = (FileNotFoundError,)


DEFAULT_RETRY_POLICY = RetryPolicy()


def _retry(
    operation: Callable[[], None], description: str, policy: RetryPolicy
) -> None:
    for attempt in range(1, policy.attempts + 1):
        try:
            operation()
            return
        except policy.retry_on as error:
            if attempt == policy.attempts:
                raise RuntimeError(
                    f"{description} failed after {policy.attempts} attempts"
                ) from error
            logger.warning(
                "Retrying transfer",
                description=description,
                attempt=attempt,
                error=str(error),
            )
            time.sleep(policy.backoff_seconds * attempt)


def _copy_file(source: Path, destination: Path, policy: RetryPolicy) -> None:
    def copy() -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)

    _retry(copy, f"copy to {destination}", policy)


def copy_pairs(
    pairs: Sequence[tuple[Path, Path]],
    transfers: int,
    policy: RetryPolicy = DEFAULT_RETRY_POLICY,
) -> None:
    with ThreadPoolExecutor(max_workers=transfers) as executor:
        futures = [
            executor.submit(_copy_file, source, destination, policy)
            for source, destination in pairs
        ]
        for future in futures:
            future.result()
