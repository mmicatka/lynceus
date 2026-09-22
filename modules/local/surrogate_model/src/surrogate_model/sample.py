# modules/local/surrogate_model/src/surrogate_model/sample.py

import logging
import sys
from enum import Enum

import click
from lynceus_utils.cli import NumWorkers
from lynceus_utils.duckdb import get_connection
from lynceus_utils.storage.blob_storage import get_blob_storage_settings
from lynceus_utils.storage.filesystem import get_filesystem
from pydantic import BaseModel

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)

logger = logging.getLogger(__name__)


class SamplingMethod(str, Enum):
    UNIFORM = "uniform"


class SampleManifest(BaseModel):
    source_glob: str
    method: SamplingMethod
    num_samples: int
    output: str
    n_sampled: int


def _manifest_matches_config(
    fs, manifest_path: str, source_glob: str, method: SamplingMethod, num_samples: int
) -> bool:
    if not fs.exists(manifest_path):
        return False
    with fs.open(manifest_path) as f:
        existing = SampleManifest.model_validate_json(f.read())
    return (
        existing.source_glob == source_glob
        and existing.method == method
        and existing.num_samples == num_samples
    )


def _build_sample_query(
    source_glob: str, method: SamplingMethod, num_samples: int
) -> str:
    if method == SamplingMethod.UNIFORM:
        return f"""
            SELECT *
            FROM read_parquet('{source_glob}')
            USING SAMPLE {num_samples} ROWS (Reservoir)
        """
    raise ValueError(f"Unsupported sampling method: {method}")


@click.command()
@click.option(
    "--input",
    type=str,
    required=True,
    help="Input folder containing Parquet files.",
)
@click.option(
    "--output", type=str, required=True, help="Path to the output Parquet file."
)
@click.option(
    "--method",
    type=click.Choice([m.value for m in SamplingMethod]),
    default=SamplingMethod.UNIFORM.value,
    show_default=True,
    help="Sampling strategy to use.",
)
@click.option(
    "--use-blob-storage",
    is_flag=True,
    help="Read input and write output via blob storage.",
)
@click.option(
    "--bucket", type=str, default="lynceus", help="S3-compatible bucket name."
)
@click.option(
    "--num-samples", type=int, required=True, help="Number of samples to draw."
)
@click.option(
    "--num-workers",
    default="auto",
    type=NumWorkers(),
    show_default=True,
    help="Number of parallel workers (integer >= 1 or 'auto').",
)
def sample(
    input: str,
    output: str,
    method: str,
    use_blob_storage: bool,
    bucket: str,
    num_samples: int,
    num_workers: int,
):
    sampling_method = SamplingMethod(method)
    source_glob = f"{input.rstrip('/')}/*.parquet"

    blob_storage_settings = None

    if use_blob_storage:
        blob_storage_settings = get_blob_storage_settings()
        source_glob = f"s3://{bucket}/{source_glob.lstrip('/')}"
        output = f"s3://{bucket}/{output.lstrip('/')}"

    conn = get_connection(blob_storage_settings, threads=num_workers)
    fs = get_filesystem(blob_storage_settings)

    manifest_path = f"{output}.manifest.json"

    if _manifest_matches_config(
        fs, manifest_path, source_glob, sampling_method, num_samples
    ):
        logger.info("Sample already exists for output=%s, skipping", output)
        return

    res = conn.sql(f"SELECT count(*) FROM read_parquet('{source_glob}')").fetchone()

    source_row_count = res[0] if res else 0

    logger.info(
        "folder=%s method=%s sampling %d rows from %d (source=%s)",
        input,
        sampling_method.value,
        num_samples,
        source_row_count,
        source_glob,
    )

    query = _build_sample_query(source_glob, sampling_method, num_samples)
    conn.sql(f"COPY ({query}) TO '{output}' (FORMAT PARQUET)")

    res = conn.sql(f"SELECT count(*) FROM read_parquet('{output}')").fetchone()

    n_sampled = res[0] if res else 0

    manifest = SampleManifest(
        source_glob=source_glob,
        method=sampling_method,
        num_samples=num_samples,
        output=output,
        n_sampled=n_sampled,
    )

    with fs.open(manifest_path, "w") as f:
        f.write(manifest.model_dump_json())
