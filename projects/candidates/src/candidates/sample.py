# projects/candidates/src/candidates/sample.py

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


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _marker_path(output_path: str) -> str:
    return f"{output_path}.success"


def _sample_is_valid(output_path: str, num_samples: int) -> bool:
    marker_path = _marker_path(output_path)
    if not (os.path.exists(output_path) and os.path.exists(marker_path)):
        return False
    with open(marker_path, "r") as f:
        return json.load(f).get("num_samples") == num_samples


def _write_success_marker(output_path: str, num_samples: int) -> None:
    with open(_marker_path(output_path), "w") as f:
        json.dump({"num_samples": num_samples}, f)


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
@wide_log(logger)
def sample_candidates(
    input_path: str,
    output_path: str,
    num_samples: int,
    num_workers: int,
) -> None:
    click.echo(f"Processing {input_path}...")

    if _sample_is_valid(output_path, num_samples):
        logger.info(
            "Sample already valid, skipping generation",
            source=input_path,
            num_samples=num_samples,
            output_path=output_path,
        )
        click.echo("Done!")
        return

    conn = duckdb.connect()
    conn.execute("SET threads = ?", [num_workers])

    logger.info(
        "Executing reservoir sampling",
        source=input_path,
        num_samples=num_samples,
        output_path=output_path,
        workers=num_workers,
    )

    _ensure_parent_dir(output_path)

    conn.sql(
        f"""
        COPY (
            SELECT *
            FROM read_parquet({_sql_literal(input_path)})
            USING SAMPLE reservoir({num_samples} ROWS)
        )
        TO {_sql_literal(output_path)}
        (FORMAT parquet, COMPRESSION zstd)
        """
    )

    _write_success_marker(output_path, num_samples)

    logger.info(
        "Finished reservoir sampling",
        source=input_path,
        num_samples=num_samples,
        output_path=output_path,
    )

    click.echo("Done!")
