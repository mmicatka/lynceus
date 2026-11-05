# projects/candidates/src/candidates/load/shard.py

import datetime
import gzip
import io
import time
from collections import defaultdict
from collections.abc import Iterator
from pathlib import Path

import click
import pyarrow as pa
import pyarrow.parquet as pq
from lynceus_core.io import staged_io
from lynceus_core.logging import get_lynceus_logger, wide_log
from lynceus_core.manifest.common import Manifest
from lynceus_core.shards.common import SHARD_HASH_SCHEME, get_shard_id

logger = get_lynceus_logger()

DEFAULT_CHUNK_SIZE = 1024 * 1024 * 32
DEFAULT_NUM_SHARDS = 512
DEFAULT_TRANSFERS = 4

SOURCE_SUFFIX = ".smi.gz"
MANIFEST_DIR = "_manifests"

PARQUET_SCHEMA = pa.schema(
    [
        pa.field("smiles", pa.string()),
        pa.field("id", pa.string()),
    ]
)

ShardBuckets = dict[int, tuple[list[str], list[str]]]


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


def _bucket_rows(path: Path, chunk_size: int, num_shards: int) -> ShardBuckets:
    buckets: ShardBuckets = defaultdict(lambda: ([], []))
    for smiles, identifier in _iter_smi_rows(path, chunk_size):
        smiles_batch, id_batch = buckets[get_shard_id(identifier, num_shards)]
        smiles_batch.append(smiles)
        id_batch.append(identifier)
    return buckets


def _write_files(
    buckets: ShardBuckets, source_path: Path, output_dir: Path
) -> list[dict]:
    files = []
    for shard_id in sorted(buckets):
        smiles_batch, id_batch = buckets[shard_id]
        relative_path = file_relative_path(shard_id, source_path)
        file_path = output_dir / relative_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        table = pa.table(
            {"smiles": smiles_batch, "id": id_batch},
            schema=PARQUET_SCHEMA,
        )
        pq.write_table(table, file_path, compression="zstd")
        files.append(
            {
                "shard_id": shard_id,
                "path": str(relative_path),
                "rows": table.num_rows,
            }
        )
    return files


def _shard_file(
    source_path: Path,
    output_dir: Path,
    chunk_size: int,
    num_shards: int,
    transfers: int,
    scratch_dir: str | None,
) -> list[dict]:
    with staged_io([source_path], output_dir, transfers, scratch_dir) as (
        local_inputs,
        local_output,
    ):
        (local_source,) = local_inputs
        buckets = _bucket_rows(local_source, chunk_size, num_shards)
        return _write_files(buckets, source_path, local_output)


@click.command("shard_candidates")
@click.option(
    "--input",
    "input_path",
    required=True,
    type=str,
    help="Input .smi.gz file.",
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
@wide_log(logger)
def shard_candidates(
    input_path: str,
    output_path: str,
    num_shards: int,
    transfers: int,
    chunk_size: int,
    scratch_dir: str | None,
):
    click.echo(f"Processing {input_path}...")

    source_path = Path(input_path)
    output_dir = Path(output_path)

    manifest = build_manifest(source_path, output_dir, num_shards)
    if manifest_is_valid(manifest):
        logger.info("Valid manifest found.", file=source_path.name)
        click.echo("Done!")
        return

    output_dir.mkdir(parents=True, exist_ok=True)

    start_time = time.perf_counter()

    files = _shard_file(
        source_path, output_dir, chunk_size, num_shards, transfers, scratch_dir
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
    click.echo("Done!")


if __name__ == "__main__":
    shard_candidates()
