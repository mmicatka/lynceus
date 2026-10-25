# libs/lynceus-core/src/lynceus_core/io/staged_io.py

import tempfile
from collections.abc import Generator, Sequence
from contextlib import contextmanager
from pathlib import Path

from lynceus_core.io.transfer import DEFAULT_RETRY_POLICY, RetryPolicy, copy_pairs


def _ensure_unique_names(paths: Sequence[Path]) -> None:
    names = [path.name for path in paths]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        raise ValueError(f"Input files share basenames: {duplicates}")


def _list_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*") if path.is_file())


@contextmanager
def staged_input(
    input_files: Sequence[Path],
    transfers: int,
    scratch_dir: str | None = None,
    retry_policy: RetryPolicy = DEFAULT_RETRY_POLICY,
) -> Generator[list[Path]]:
    _ensure_unique_names(input_files)
    with tempfile.TemporaryDirectory(dir=scratch_dir) as scratch:
        local_files = [Path(scratch) / path.name for path in input_files]
        copy_pairs(list(zip(input_files, local_files)), transfers, retry_policy)
        yield local_files


@contextmanager
def staged_output(
    output_path: Path,
    transfers: int,
    scratch_dir: str | None = None,
    retry_policy: RetryPolicy = DEFAULT_RETRY_POLICY,
) -> Generator[Path]:
    with tempfile.TemporaryDirectory(dir=scratch_dir) as scratch:
        local_output = Path(scratch)
        yield local_output
        copy_pairs(
            [
                (path, output_path / path.relative_to(local_output))
                for path in _list_files(local_output)
            ],
            transfers,
            retry_policy,
        )


@contextmanager
def staged_io(
    input_files: Sequence[Path],
    output_path: Path,
    transfers: int,
    scratch_dir: str | None = None,
    retry_policy: RetryPolicy = DEFAULT_RETRY_POLICY,
) -> Generator[tuple[list[Path], Path]]:
    with (
        staged_input(input_files, transfers, scratch_dir, retry_policy) as local_inputs,
        staged_output(
            output_path, transfers, scratch_dir, retry_policy
        ) as local_output,
    ):
        yield local_inputs, local_output
