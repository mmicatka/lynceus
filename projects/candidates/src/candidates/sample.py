# projects/candidates/src/candidates/sample.py

import datetime
import os
import time

import click
import duckdb
from lynceus_core.cli import NumWorkers
from lynceus_core.logging import get_lynceus_logger, wide_log
from lynceus_core.manifest.common import Manifest

logger = get_lynceus_logger()


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _ensure_parent_dir(path: str) -> None:
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)


@click.command("sample_reservoir")
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
    type=click.Path(dir_okay=False, writable=True),
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
    default=42,
    type=int,
    show_default=True,
    help="Random seed for repeatable reservoir sampling.",
)
@wide_log(logger)
def sample_candidates(
    input_path: str,
    output_path: str,
    num_samples: int,
    num_workers: int,
    seed: int,
) -> None:
    click.echo(f"Processing {input_path}...")

    expected_state = {
        "num_samples": num_samples,
        "seed": seed,
        "input_path": os.path.abspath(input_path),
    }

    manifest_path = f"{output_path}.manifest"
    disk_manifest = Manifest(filepath=manifest_path)

    target_manifest = Manifest(data=expected_state)

    if disk_manifest.exists():
        try:
            disk_manifest.load()
            if target_manifest <= disk_manifest:
                logger.info(
                    "Sample already valid, skipping generation",
                    source=input_path,
                    num_samples=num_samples,
                    seed=seed,
                    output_path=output_path,
                )
                click.echo("Done!")
                return
        except Exception as e:
            logger.warning(
                "Failed to load existing manifest, re-generating.", error=str(e)
            )

    start_time = time.perf_counter()

    conn = duckdb.connect()
    conn.execute("SET threads = ?", [num_workers])

    logger.info(
        "Executing reservoir sampling",
        source=input_path,
        num_samples=num_samples,
        seed=seed,
        output_path=output_path,
        workers=num_workers,
    )

    _ensure_parent_dir(output_path)

    conn.sql(
        f"""
        COPY (
            SELECT *
            FROM read_parquet({_sql_literal(input_path)})
            USING SAMPLE reservoir({num_samples} ROWS) REPEATABLE ({seed})
        )
        TO {_sql_literal(output_path)}
        (FORMAT parquet, COMPRESSION zstd)
        """
    )

    target_manifest.data = expected_state
    elapsed_time = time.perf_counter() - start_time
    target_manifest.data["run_time"] = str(datetime.timedelta(seconds=elapsed_time))
    target_manifest.save()

    logger.info(
        "Finished reservoir sampling",
        source=input_path,
        num_samples=num_samples,
        seed=seed,
        output_path=output_path,
    )

    click.echo("Done!")
