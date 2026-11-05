# libs/lynceus-core/src/lynceus_core/io/retry.py


import errno
import time
from collections.abc import Callable
from dataclasses import dataclass

from lynceus_core.logging import get_lynceus_logger

logger = get_lynceus_logger()


@dataclass(frozen=True)
class RetryPolicy:
    attempts: int = 5
    backoff_seconds: float = 2.0
    retry_on: tuple[type[OSError], ...] = (FileNotFoundError,)
    errnos: frozenset[int] = frozenset({errno.EIO})

    def __post_init__(self) -> None:
        if self.attempts < 1:
            raise ValueError(f"attempts must be >= 1, got {self.attempts}")

    def is_retryable(self, error: OSError) -> bool:
        return isinstance(error, self.retry_on) or error.errno in self.errnos


DEFAULT_RETRY_POLICY = RetryPolicy()


def retry_call[T](
    operation: Callable[[], T], description: str, policy: RetryPolicy
) -> T:
    for attempt in range(1, policy.attempts):
        try:
            return operation()
        except OSError as error:
            if not policy.is_retryable(error):
                raise
            logger.warning(
                "Retrying after OS error",
                description=description,
                attempt=attempt,
                max_attempts=policy.attempts,
                errno=error.errno,
                error=str(error),
            )
            time.sleep(policy.backoff_seconds * attempt)

    try:
        return operation()
    except OSError as error:
        if not policy.is_retryable(error):
            raise
        raise RuntimeError(
            f"{description} failed after {policy.attempts} attempts"
        ) from error
