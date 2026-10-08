# projects/candidates/src/candidates/sample.py

import glob
import json
import os
import sys

import click
import duckdb
import structlog
from lynceus_core.cli import NumWorkers
from lynceus_core.logging import wide_log


def configure_logging():
    if sys.stdout.isatty():
        processor = structlog.dev.ConsoleRenderer(colors=True)
    else:
        processor = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            processor,
        ]
    )


configure_logging()
logger = structlog.get_logger()


def _marker_path(output_path: str, input_folder: str) -> str:
    return os.path.join(output_path, f"_SUCCESS_{input_folder}")


def _partition_is_valid(
    output_path: str, num_samples: int, rows_per_file: int, input_folder: str
) -> bool:
    marker_path = _marker_path(output_path, input_folder)
    if not os.path.exists(marker_path):
        return False
    with open(marker_path, "r") as f:
        data = json.load(f)
        return (
            data.get("num_samples") == num_samples
            and data.get("rows_per_file") == rows_per_file
        )


def _write_success_marker(
    output_path: str, num_samples: int, rows_per_file: int, input_folder: str
) -> None:
    os.makedirs(output_path, exist_ok=True)
    with open(_marker_path(output_path, input_folder), "w") as f:
        json.dump({"num_samples": num_samples, "rows_per_file": rows_per_file}, f)


@click.command("sample_reservoir")
@click.option(
    "--input",
    "input_path",
    required=True,
    type=str,
    help="Input folder containing parquet files.",
)
@click.option("--output", "output_path", required=True, type=str, help="Output folder.")
@click.option(
    "--num-samples",
    "num_samples",
    required=True,
    type=click.IntRange(min=1),
    help="Approximate total number of samples to pull.",
)
@click.option(
    "--rows-per-file",
    "rows_per_file",
    default=50000,
    show_default=True,
    type=click.IntRange(min=1),
    help="Target row count per output file for partitioning.",
)
@click.option(
    "--num-workers",
    default="auto",
    type=NumWorkers(),
    show_default=True,
    help="Number of parallel workers (integer >= 1 or 'auto').",
)
@wide_log(logger)
def sample_candidates(
    input_path: str,
    output_path: str,
    num_samples: int,
    rows_per_file: int,
    num_workers: int,
) -> None:
    click.echo(f"Processing {input_path}...")

    conn = duckdb.connect()
    conn.execute("SET threads = ?", [num_workers])

    input_folder = os.path.basename(input_path.rstrip("/"))
    source_glob = os.path.join(input_path, "*.parquet")

    if not glob.glob(source_glob):
        raise RuntimeError(
            f"folder={input_folder} resolved to zero parquet files at {source_glob}"
        )

    if _partition_is_valid(output_path, num_samples, rows_per_file, input_folder):
        logger.info(
            "Sample already valid, skipping generation",
            folder=input_folder,
            num_samples=num_samples,
            rows_per_file=rows_per_file,
            output_path=output_path,
        )
        click.echo("Done!")
        return

    logger.info(
        "Executing reservoir sampling",
        source=source_glob,
        num_samples=num_samples,
        rows_per_file=rows_per_file,
        output_path=output_path,
        workers=num_workers,
    )

    os.makedirs(output_path, exist_ok=True)

    conn.sql(
        f"""
        COPY (
            SELECT *, (row_number() OVER () / {rows_per_file})::INT AS file_id
            FROM read_parquet('{source_glob}')
            USING SAMPLE reservoir({num_samples} ROWS)
        )
        TO '{output_path}'
        (FORMAT parquet, COMPRESSION zstd, PARTITION_BY (file_id), OVERWRITE_OR_IGNORE,
        FILENAME_PATTERN '{input_folder}_{{i}}')
        """
    )

    _write_success_marker(output_path, num_samples, rows_per_file, input_folder)

    logger.info(
        "Finished reservoir sampling",
        folder=input_folder,
        num_samples=num_samples,
        rows_per_file=rows_per_file,
        output_path=output_path,
    )

    click.echo("Done!")
