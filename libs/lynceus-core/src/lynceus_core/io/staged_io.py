# libs/lynceus-core/src/lynceus_core/io/staged_io.py

import shutil
import tempfile
from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path


def _copy_tree(source: Path, destination: Path, transfers: int, pattern: str) -> None:
    files = [path for path in source.glob(pattern) if path.is_file()]
    for directory in {destination / path.parent.relative_to(source) for path in files}:
        directory.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=transfers) as executor:
        futures = [
            executor.submit(
                shutil.copyfile, path, destination / path.relative_to(source)
            )
            for path in files
        ]
        for future in futures:
            future.result()


@contextmanager
def staged_io(
    input_path: str,
    output_path: str,
    transfers: int,
    scratch_dir: str | None = None,
) -> Generator[tuple[Path, Path]]:
    with tempfile.TemporaryDirectory(dir=scratch_dir) as scratch:
        local_input = Path(scratch) / "input"
        local_output = Path(scratch) / "output"
        local_input.mkdir()
        local_output.mkdir()
        _copy_tree(Path(input_path), local_input, transfers, "*.parquet")
        yield local_input, local_output
        _copy_tree(local_output, Path(output_path), transfers, "**/*")
