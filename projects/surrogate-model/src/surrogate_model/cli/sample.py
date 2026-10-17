# projects/surrogate-model/src/surrogate_model/cli/sample.py

import glob
import json
import os
import sys
from pathlib import Path

import click
import duckdb
import structlog
from lynceus_core.cli import NumWorkers
from lynceus_core.logging import wide_log

PARQUET_PATTERN = "*.parquet"
MARKER_SUFFIX = ".success"
TEMP_SUFFIX = ".tmp"


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


def _quote_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _marker_path(output_path: str) -> str:
    return f"{output_path}{MARKER_SUFFIX}"


def _output_is_valid(output_path: str, num_samples: int) -> bool:
    marker_path = _marker_path(output_path)
    if not (os.path.isfile(output_path) and os.path.isfile(marker_path)):
        return False
    with open(marker_path, "r") as f:
        return json.load(f).get("num_samples") == num_samples


def _write_success_marker(output_path: str, num_samples: int) -> None:
    with open(_marker_path(output_path), "w") as f:
        json.dump({"num_samples": num_samples}, f)


def _resolve_parquet_files(pattern: str) -> list[str]:
    files: list[str] = []
    for match in sorted(glob.glob(pattern, recursive=True)):
        if os.path.isdir(match):
            files.extend(sorted(glob.glob(os.path.join(match, PARQUET_PATTERN))))
        else:
            files.append(match)

    unique_files = list(dict.fromkeys(files))
    if not unique_files:
        raise RuntimeError(f"Resolved zero parquet files at {pattern}")
    return unique_files


def _sample_aligned(
    conn: duckdb.DuckDBPyConnection,
    features_files: list[str],
    conformers_files: list[str],
    output_file: str,
    num_samples: int,
    id_column: str,
) -> None:
    column = _quote_identifier(id_column)
    conn.execute(
        f"""
        COPY (
            SELECT
                f.*,
                c.conformer
            FROM read_parquet(?) f
            JOIN read_parquet(?) c
              ON f.{column} = c.{column}
            USING SAMPLE reservoir({num_samples} ROWS)
        )
        TO {_quote_literal(output_file)}
        (FORMAT parquet, COMPRESSION zstd)
        """,
        [features_files, conformers_files],
    )


def _write_sample_atomically(
    conn: duckdb.DuckDBPyConnection,
    features_files: list[str],
    conformers_files: list[str],
    output_path: str,
    num_samples: int,
    id_column: str,
) -> None:
    temp_path = f"{output_path}{TEMP_SUFFIX}"
    _sample_aligned(
        conn=conn,
        features_files=features_files,
        conformers_files=conformers_files,
        output_file=temp_path,
        num_samples=num_samples,
        id_column=id_column,
    )
    os.replace(temp_path, output_path)


@click.command("sample_aligned")
@click.option(
    "--features-input",
    "features_input",
    required=True,
    type=str,
    help="Features parquet file, glob pattern, or folder of parquet files.",
)
@click.option(
    "--conformers-input",
    "conformers_input",
    required=True,
    type=str,
    help="Conformer parquet file, glob pattern, or folder of parquet files.",
)
@click.option(
    "--output",
    "output_path",
    required=True,
    type=click.Path(dir_okay=False),
    help="Output parquet file path.",
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

    identifier = Path(output_path).stem

    if _output_is_valid(output_path, num_samples):
        logger.info(
            "Sample already valid, skipping generation",
            identifier=identifier,
            num_samples=num_samples,
            output_path=output_path,
        )
        click.echo("Done!")
        return

    features_files = _resolve_parquet_files(features_input)
    conformers_files = _resolve_parquet_files(conformers_input)

    logger.info(
        "Executing aligned reservoir sampling",
        features_source=features_input,
        conformers_source=conformers_input,
        num_features_files=len(features_files),
        num_conformers_files=len(conformers_files),
        identifier=identifier,
        num_samples=num_samples,
        output_path=output_path,
        workers=num_workers,
    )

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    conn = duckdb.connect()
    conn.execute("SET threads = ?", [num_workers])
    conn.execute("SET arrow_large_buffer_size=true")

    _write_sample_atomically(
        conn=conn,
        features_files=features_files,
        conformers_files=conformers_files,
        output_path=output_path,
        num_samples=num_samples,
        id_column=id_column,
    )

    _write_success_marker(output_path, num_samples)

    logger.info(
        "Finished aligned reservoir sampling",
        identifier=identifier,
        num_samples=num_samples,
        output_path=output_path,
    )
    click.echo("Done!")
