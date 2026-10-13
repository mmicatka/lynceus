# libs/lynceus-core/src/lynceus_core/io/staged_io.py

import shutil
import tempfile
import time
from collections.abc import Callable, Generator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import structlog

logger = structlog.get_logger()


@dataclass(frozen=True)
class RetryPolicy:
    attempts: int = 5
    backoff_seconds: float = 0.5


def _retry_on_missing_path(
    operation: Callable[[], None], description: str, policy: RetryPolicy
) -> None:
    for attempt in range(1, policy.attempts + 1):
        try:
            operation()
            return
        except FileNotFoundError as error:
            if attempt == policy.attempts:
                raise RuntimeError(
                    f"{description} failed after {policy.attempts} attempts"
                ) from error
            logger.warning(
                "Retrying after missing path",
                description=description,
                attempt=attempt,
                error=str(error),
            )
            time.sleep(policy.backoff_seconds * attempt)


def _copy_file(source: Path, destination: Path, policy: RetryPolicy) -> None:
    def copy() -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)

    _retry_on_missing_path(copy, f"copy to {destination}", policy)


def _copy_tree(
    source: Path,
    destination: Path,
    transfers: int,
    pattern: str,
    policy: RetryPolicy,
) -> None:
    files = [path for path in source.glob(pattern) if path.is_file()]
    with ThreadPoolExecutor(max_workers=transfers) as executor:
        futures = [
            executor.submit(
                _copy_file, path, destination / path.relative_to(source), policy
            )
            for path in files
        ]
        for future in futures:
            future.result()


def _copy_pairs(
    pairs: Sequence[tuple[Path, Path]],
    transfers: int,
    policy: RetryPolicy,
) -> None:
    with ThreadPoolExecutor(max_workers=transfers) as executor:
        futures = [
            executor.submit(_copy_file, source, destination, policy)
            for source, destination in pairs
        ]
        for future in futures:
            future.result()


@contextmanager
def staged_io(
    input_files: Sequence[Path],
    output_path: Path,
    transfers: int,
    scratch_dir: str | None = None,
    retry_policy: RetryPolicy = RetryPolicy(),
) -> Generator[tuple[Path, Path]]:
    with tempfile.TemporaryDirectory(dir=scratch_dir) as scratch:
        local_input = Path(scratch) / "input"
        local_output = Path(scratch) / "output"
        local_input.mkdir()
        local_output.mkdir()
        _copy_pairs(
            [(path, local_input / path.name) for path in input_files],
            transfers,
            retry_policy,
        )
        yield local_input, local_output
        _copy_pairs(
            [
                (path, output_path / path.relative_to(local_output))
                for path in sorted(local_output.rglob("*"))
                if path.is_file()
            ],
            transfers,
            retry_policy,
        )
