# projects/surrogate-model/src/surrogate_model/cli/sample.py

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


def _marker_path(output_path: str, identifier: str) -> str:
    return os.path.join(output_path, f"_SUCCESS_{identifier}")


def _partition_is_valid(output_path: str, num_samples: int, identifier: str) -> bool:
    marker_path = _marker_path(output_path, identifier)
    if not os.path.exists(marker_path):
        return False
    with open(marker_path, "r") as f:
        data = json.load(f)
        return data.get("num_samples") == num_samples


def _write_success_marker(output_path: str, num_samples: int, identifier: str) -> None:
    os.makedirs(output_path, exist_ok=True)
    with open(_marker_path(output_path, identifier), "w") as f:
        json.dump({"num_samples": num_samples}, f)


def _sample_aligned(
    conn: duckdb.DuckDBPyConnection,
    features_glob: str,
    conformers_glob: str,
    features_out: str,
    conformers_out: str,
    features_folder: str,
    num_samples: int,
    id_column: str,
) -> None:

    conn.execute(
        f"""
        CREATE TEMP TABLE joined_sample AS
        SELECT
            f.*,
            c.conformer
        FROM read_parquet('{features_glob}') f
        JOIN read_parquet('{conformers_glob}') c
          ON f.{id_column} = c.{id_column}
        USING SAMPLE reservoir({num_samples} ROWS);
        """
    )

    conn.sql(
        f"""
        COPY (SELECT * EXCLUDE (conformer) FROM joined_sample)
        TO '{features_out}'
        (FORMAT parquet, COMPRESSION zstd, OVERWRITE_OR_IGNORE, FILENAME_PATTERN
        '{features_folder}_features_{{i}}')
        """
    )

    conn.sql(
        f"""
        COPY (SELECT {id_column}, conformer FROM joined_sample)
        TO '{conformers_out}'
        (FORMAT parquet, COMPRESSION zstd, OVERWRITE_OR_IGNORE, FILENAME_PATTERN
        '{features_folder}_conformers_{{i}}')
        """
    )


@click.command("sample_aligned")
@click.option(
    "--features-input",
    "features_input",
    required=True,
    type=str,
    help="Input folder for features parquet files.",
)
@click.option(
    "--conformers-input",
    "conformers_input",
    required=True,
    type=str,
    help="Input folder for conformer parquet files.",
)
@click.option(
    "--output",
    "output_path",
    required=True,
    type=str,
    help="Base output folder for sampled results.",
)
@click.option(
    "--num-samples",
    "num_samples",
    required=True,
    type=click.IntRange(min=1),
    help="Total number of samples to pull.",
)
@click.option(
    "--id-column",
    "id_column",
    default="id",
    show_default=True,
    type=str,
    help="Shared ID column to join on.",
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
    features_input: str,
    conformers_input: str,
    output_path: str,
    num_samples: int,
    id_column: str,
    num_workers: int,
) -> None:
    click.echo(
        f"Processing aligned samples from {features_input} and {conformers_input}..."
    )

    features_folder = os.path.basename(features_input.rstrip("/"))
    features_glob = os.path.join(features_input, "*.parquet")
    conformers_glob = os.path.join(conformers_input, "*.parquet")

    if not glob.glob(features_glob):
        raise RuntimeError(f"Resolved zero parquet files at {features_glob}")
    if not glob.glob(conformers_glob):
        raise RuntimeError(f"Resolved zero parquet files at {conformers_glob}")

    if _partition_is_valid(output_path, num_samples, features_folder):
        logger.info(
            "Sample already valid, skipping generation",
            identifier=features_folder,
            num_samples=num_samples,
            output_path=output_path,
        )
        click.echo("Done!")
        return

    logger.info(
        "Executing aligned reservoir sampling",
        features_source=features_glob,
        conformers_source=conformers_glob,
        num_samples=num_samples,
        output_path=output_path,
        workers=num_workers,
    )

    os.makedirs(output_path, exist_ok=True)
    features_out = os.path.join(output_path, "features")
    conformers_out = os.path.join(output_path, "conformers")

    conn = duckdb.connect()
    conn.execute("SET threads = ?", [num_workers])
    conn.execute("SET arrow_large_buffer_size=true")

    _sample_aligned(
        conn=conn,
        features_glob=features_glob,
        conformers_glob=conformers_glob,
        features_out=features_out,
        conformers_out=conformers_out,
        features_folder=features_folder,
        num_samples=num_samples,
        id_column=id_column,
    )

    _write_success_marker(output_path, num_samples, features_folder)

    logger.info(
        "Finished aligned reservoir sampling",
        identifier=features_folder,
        num_samples=num_samples,
        output_path=output_path,
    )
    click.echo("Done!")
