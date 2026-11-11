# projects/candidates/src/candidates/load/shard.py


import datetime
import gzip
import io
import time
from collections import defaultdict
from collections.abc import Iterator
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import click
import pyarrow as pa
import pyarrow.parquet as pq
from lynceus_core.cli import NumWorkers
from lynceus_core.io import staged_io
from lynceus_core.logging import get_lynceus_logger, wide_log
from lynceus_core.manifest.common import Manifest
from lynceus_core.shards.common import SHARD_HASH_SCHEME, get_shard_id

logger = get_lynceus_logger()

DEFAULT_CHUNK_SIZE = 1024 * 1024 * 32
DEFAULT_NUM_SHARDS = 512
DEFAULT_TRANSFERS = 4
DEFAULT_MAX_BUFFERED_ROWS = 5_000_000

SOURCE_SUFFIX = ".smi.gz"
MANIFEST_DIR = "_manifests"

PARQUET_SCHEMA = pa.schema(
    [
        pa.field("smiles", pa.string()),
        pa.field("id", pa.string()),
    ]
)


class ShardWriterPool:
    def __init__(
        self,
        source_path: Path,
        output_dir: Path,
        max_buffered_rows: int,
    ):
        self._source_path = source_path
        self._output_dir = output_dir
        self._max_buffered_rows = max_buffered_rows
        self._buffers: dict[int, tuple[list[str], list[str]]] = defaultdict(
            lambda: ([], [])
        )
        self._buffered_rows = 0
        self._writers: dict[int, pq.ParquetWriter] = {}
        self._row_counts: dict[int, int] = defaultdict(int)

    def __enter__(self) -> "ShardWriterPool":
        return self

    def __exit__(self, exc_type: type[BaseException] | None, *_: object) -> None:
        try:
            if exc_type is None:
                self._flush()
        finally:
            self._close()

    def add(self, shard_id: int, smiles: str, identifier: str) -> None:
        smiles_batch, id_batch = self._buffers[shard_id]
        smiles_batch.append(smiles)
        id_batch.append(identifier)
        self._buffered_rows += 1
        if self._buffered_rows >= self._max_buffered_rows:
            self._flush()

    def files(self) -> list[dict]:
        return [
            {
                "shard_id": shard_id,
                "path": str(file_relative_path(shard_id, self._source_path)),
                "rows": self._row_counts[shard_id],
            }
            for shard_id in sorted(self._writers)
        ]

    def _writer_for(self, shard_id: int) -> pq.ParquetWriter:
        if shard_id not in self._writers:
            file_path = self._output_dir / file_relative_path(
                shard_id, self._source_path
            )
            file_path.parent.mkdir(parents=True, exist_ok=True)
            self._writers[shard_id] = pq.ParquetWriter(
                file_path, PARQUET_SCHEMA, compression="zstd"
            )
        return self._writers[shard_id]

    def _flush(self) -> None:
        for shard_id, (smiles_batch, id_batch) in self._buffers.items():
            if not smiles_batch:
                continue
            table = pa.table(
                {"smiles": smiles_batch, "id": id_batch}, schema=PARQUET_SCHEMA
            )
            self._writer_for(shard_id).write_table(table)
            self._row_counts[shard_id] += table.num_rows
        self._buffers.clear()
        self._buffered_rows = 0

    def _close(self) -> None:
        for writer in self._writers.values():
            writer.close()


def _shard_file(
    source_path: Path,
    output_dir: Path,
    chunk_size: int,
    num_shards: int,
    transfers: int,
    scratch_dir: str | None,
    max_buffered_rows: int,
) -> list[dict]:
    with staged_io([source_path], output_dir, transfers, scratch_dir) as (
        local_inputs,
        local_output,
    ):
        (local_source,) = local_inputs
        with ShardWriterPool(source_path, local_output, max_buffered_rows) as pool:
            for smiles, identifier in _iter_smi_rows(local_source, chunk_size):
                pool.add(get_shard_id(identifier, num_shards), smiles, identifier)
        return pool.files()


def source_stem(source_path: Path) -> str:
    name = source_path.name
    return name[: -len(SOURCE_SUFFIX)] if name.endswith(SOURCE_SUFFIX) else name


def manifest_path(source_path: Path, output_dir: Path) -> Path:
    return output_dir / MANIFEST_DIR / f"{source_stem(source_path)}.manifest.json"


def file_relative_path(shard_id: int, source_path: Path) -> Path:
    return Path(f"shard_id={shard_id}") / f"{source_stem(source_path)}.parquet"


def build_manifest(source_path: Path, output_dir: Path, num_shards: int) -> Manifest:
    manifest = Manifest(
        data={
            "hash": SHARD_HASH_SCHEME,
            "num_shards": num_shards,
        },
        filepath=str(manifest_path(source_path, output_dir)),
    )
    manifest.set_source_files([str(source_path)], root=str(source_path.parent))
    return manifest


def manifest_is_valid(manifest: Manifest) -> bool:
    try:
        return manifest.exists_superset()
    except Exception as e:
        logger.warning("Failed to load existing manifest, re-generating.", error=str(e))
        return False


def _parse_smi_line(line: str) -> tuple[str, str] | None:
    stripped = line.strip()
    if not stripped:
        return None
    parts = stripped.split(None, 1)
    if len(parts) < 2:
        raise RuntimeError(f"line has no ZINC id: {stripped!r}")
    return parts[0], parts[1]


def _iter_smi_rows(path: Path, chunk_size: int) -> Iterator[tuple[str, str]]:
    with open(path, "rb", buffering=chunk_size) as raw:
        with gzip.GzipFile(fileobj=raw) as gz:
            with io.TextIOWrapper(gz, encoding="utf-8", newline="") as text_stream:
                for line in text_stream:
                    parsed = _parse_smi_line(line)
                    if parsed is not None:
                        yield parsed


def _process_source(
    source_path: Path,
    output_dir: Path,
    num_shards: int,
    transfers: int,
    chunk_size: int,
    scratch_dir: str | None,
    max_buffered_rows: int,
) -> None:
    manifest = build_manifest(source_path, output_dir, num_shards)
    if manifest_is_valid(manifest):
        logger.info("Valid manifest found.", file=source_path.name)
        return

    output_dir.mkdir(parents=True, exist_ok=True)

    start_time = time.perf_counter()
    files = _shard_file(
        source_path,
        output_dir,
        chunk_size,
        num_shards,
        transfers,
        scratch_dir,
        max_buffered_rows,
    )
    elapsed_time = time.perf_counter() - start_time

    manifest.data["run_time"] = str(datetime.timedelta(seconds=elapsed_time))
    manifest.data["files"] = files
    manifest.save()

    logger.info(
        "Sharded file",
        file=source_path.name,
        files=len(files),
        rows=sum(f["rows"] for f in files),
    )


@click.command("shard_candidates")
@click.option(
    "--input",
    "input_paths",
    required=True,
    multiple=True,
    type=str,
    help="Input .smi.gz file. Repeat to process several files concurrently.",
)
@click.option(
    "--output",
    "output_path",
    required=True,
    type=str,
    help="Output folder for shards.",
)
@click.option(
    "--num-shards",
    type=click.IntRange(min=1),
    default=DEFAULT_NUM_SHARDS,
    show_default=True,
    help="Number of shards rows are hashed into by ZINC id.",
)
@click.option(
    "--transfers",
    type=click.IntRange(min=1),
    default=DEFAULT_TRANSFERS,
    show_default=True,
    help="Concurrent file transfers when staging inputs and outputs.",
)
@click.option(
    "--chunk-size",
    type=int,
    default=DEFAULT_CHUNK_SIZE,
    show_default=True,
    help="Read buffer size in bytes for streaming decompression.",
)
@click.option(
    "--scratch-dir",
    type=str,
    default=None,
    help="Local scratch directory for staging. Defaults to the system temp dir.",
)
@click.option(
    "--max-buffered-rows",
    type=click.IntRange(min=1),
    default=DEFAULT_MAX_BUFFERED_ROWS,
    show_default=True,
    help="Max rows held in memory across all shards before flushing to disk, per file.",
)
@click.option(
    "--num-workers",
    "num_workers",
    default="auto",
    type=NumWorkers(),
    show_default=True,
    help="Number of files processed concurrently (integer >= 1 or 'auto').",
)
@wide_log(logger)
def shard_candidates(
    input_paths: tuple[str, ...],
    output_path: str,
    num_shards: int,
    transfers: int,
    chunk_size: int,
    scratch_dir: str | None,
    max_buffered_rows: int,
    num_workers: int,
):
    sources = [Path(path) for path in input_paths]
    output_dir = Path(output_path)
    max_workers = min(num_workers, len(sources))

    click.echo(f"Processing {len(sources)} file(s) with {max_workers} workers...")

    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(
                _process_source,
                source,
                output_dir,
                num_shards,
                transfers,
                chunk_size,
                scratch_dir,
                max_buffered_rows // max_workers,
            )
            for source in sources
        ]
        for future in futures:
            future.result()

    click.echo("Done!")


if __name__ == "__main__":
    shard_candidates()
