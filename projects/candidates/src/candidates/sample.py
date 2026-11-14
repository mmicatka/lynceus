# projects/candidates/src/candidates/sample.py

import datetime
import time
from pathlib import Path

import click
import duckdb
from lynceus_core.cli import MemoryLimit, NumWorkers
from lynceus_core.io.staged_io import staged_output
from lynceus_core.logging import get_lynceus_logger, wide_log
from lynceus_core.manifest.common import Manifest

STAGED_OUTPUT_TRANSFERS = 1

RUN_TIME_KEY = "run_time"

MANIFEST_FILE_SUFFIX = ".manifest.json"

logger = get_lynceus_logger()


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _input_manifest(
    input_path: str,
    output_path: str,
    source_root: Path,
    expected_state: dict,
) -> Manifest:
    manifest_path = Path(output_path).with_suffix(MANIFEST_FILE_SUFFIX)
    return Manifest(filepath=manifest_path, data=expected_state).set_source_files(
        [input_path], source_root
    )


def _already_sampled(manifest: Manifest, output_path: str) -> bool:
    return Path(output_path).is_file() and manifest.exists_superset()


def _connect(num_workers: int, memory_limit: str | None) -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect()
    conn.execute("SET threads = ?", [num_workers])
    if memory_limit is not None:
        conn.execute(f"SET memory_limit={_sql_literal(memory_limit)}")
    return conn


def _write_sampled_file(
    conn: duckdb.DuckDBPyConnection,
    input_path: str,
    output_path: str,
    num_samples: int,
    seed: int,
) -> None:
    conn.execute(
        f"""
        COPY (
            SELECT *
            FROM read_parquet(?)
            USING SAMPLE reservoir({int(num_samples)} ROWS) REPEATABLE ({int(seed)})
        )
        TO {_sql_literal(output_path)}
        (FORMAT parquet, COMPRESSION zstd)
        """,
        [input_path],
    )


def _sample_via_staged_output(
    input_path: str,
    output_path: Path,
    num_samples: int,
    seed: int,
    num_workers: int,
    memory_limit: str | None,
    scratch_dir: str | None,
) -> None:
    conn = _connect(num_workers, memory_limit)
    try:
        with staged_output(
            output_path.parent,
            transfers=STAGED_OUTPUT_TRANSFERS,
            scratch_dir=scratch_dir,
        ) as local_output:
            local_file = local_output / output_path.name
            _write_sampled_file(conn, input_path, str(local_file), num_samples, seed)
    finally:
        conn.close()


@click.command("sample_reservoir")
@click.option(
    "--source-root",
    required=True,
    type=click.Path(file_okay=False, path_type=Path),
    help="Directory to base the relative paths on in the manifest.",
)
@click.option(
    "--input",
    "input_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False, readable=True),
    help="Input parquet file.",
)
@click.option(
    "--output",
    "output_path",
    required=True,
    type=str,
    help="Output parquet file.",
)
@click.option(
    "--num-samples",
    "num_samples",
    required=True,
    type=click.IntRange(min=1),
    help="Approximate total number of samples to pull.",
)
@click.option(
    "--num-workers",
    default="auto",
    type=NumWorkers(),
    show_default=True,
    help="Number of parallel workers (integer >= 1 or 'auto').",
)
@click.option(
    "--seed",
    "seed",
    default=1000,
    type=int,
    show_default=True,
    help="Random seed for repeatable reservoir sampling.",
)
@click.option(
    "--memory-limit",
    "memory_limit",
    default=None,
    type=MemoryLimit(),
    help="DuckDB memory limit, e.g. '48Gi' or '48GB'.",
)
@click.option(
    "--scratch-dir",
    type=str,
    default=None,
    help="Local directory for the sampled file before it is copied to --output "
    "(defaults to the system temp directory).",
)
@wide_log(logger)
def sample_candidates(
    source_root: Path,
    input_path: str,
    output_path: str,
    num_samples: int,
    num_workers: int,
    seed: int,
    memory_limit: str | None,
    scratch_dir: str | None,
) -> None:
    click.echo(f"Processing {input_path}...")

    expected_state = {"num_samples": num_samples, "seed": seed}
    manifest = _input_manifest(input_path, output_path, source_root, expected_state)

    try:
        if _already_sampled(manifest, output_path):
            logger.info("Valid manifest found.", manifest=manifest.data)
            click.echo("Done!")
            return
    except Exception as e:
        logger.warning("Failed to load existing manifest, re-generating.", error=str(e))

    logger.info(
        "Executing reservoir sampling",
        source=input_path,
        num_samples=num_samples,
        seed=seed,
        output_path=output_path,
        source_root=str(source_root),
        workers=num_workers,
        memory_limit=memory_limit,
        scratch_dir=scratch_dir,
    )

    start_time = time.perf_counter()

    _sample_via_staged_output(
        input_path,
        Path(output_path),
        num_samples,
        seed,
        num_workers,
        memory_limit,
        scratch_dir,
    )

    elapsed_time = time.perf_counter() - start_time
    manifest.data[RUN_TIME_KEY] = str(datetime.timedelta(seconds=elapsed_time))
    manifest.save()

    logger.info("Finished reservoir sampling", manifest=manifest.data)
    click.echo("Done!")
