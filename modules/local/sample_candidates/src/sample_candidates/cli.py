# modules/local/sample_candidates/src/sample_candidates/cli.py

from __future__ import annotations

from pathlib import Path

import click
from lynceus_utils.duckdb import file_exists, get_connection
from lynceus_utils.storage import BlobStorageSettings, get_blob_storage_settings

from sample_candidates.binning import fit_quantile_bins
from sample_candidates.config import StratificationConfig
from sample_candidates.projection import fit_projection, project_batch
from sample_candidates.sampling import build_capped_sample_query


def _resolve_path(
    path: str, blob_storage_settings: BlobStorageSettings | None, bucket: str
) -> str:
    if blob_storage_settings is None:
        return path
    return f"s3://{bucket}/{path.lstrip('/')}"


@click.command()
@click.option(
    "--input-path",
    required=True,
    help="Parquet glob (local path or S3 prefix) of raw candidate shards"
    " to sample from.",
)
@click.option(
    "--output",
    "output_path",
    required=True,
    type=str,
    help="Path to write the capped stratified sample (Parquet) to.",
)
@click.option(
    "--fingerprint-field",
    default="morgan_fp",
    show_default=True,
    help="Column name holding the Morgan fingerprint bit vector.",
)
@click.option(
    "--fingerprint-n-bits",
    default=1024,
    show_default=True,
    type=int,
    help="Length of the Morgan fingerprint bit vector.",
)
@click.option(
    "--property-field",
    "property_fields",
    multiple=True,
    default=("mw", "logp", "tpsa"),
    show_default=True,
    help="Physicochemical property column to include. Repeatable.",
)
@click.option(
    "--n-projected-dims",
    default=8,
    show_default=True,
    type=int,
    help="Number of dimensions to random-project the combined feature vector into.",
)
@click.option(
    "--projection-density",
    default=1.0 / 3.0,
    show_default=True,
    type=float,
    help="Fraction of nonzero entries per row in the sparse random projection matrix.",
)
@click.option(
    "--random-seed",
    default=0,
    show_default=True,
    type=int,
    help="Random seed for the projection and tie-breaking in sampling.",
)
@click.option(
    "--n-quantiles-per-dim",
    default=10,
    show_default=True,
    type=int,
    help="Number of quantile bins per projected dimension.",
)
@click.option(
    "--cap-per-stratum",
    default=500,
    show_default=True,
    type=int,
    help="Maximum number of rows drawn from any single stratum.",
)
@click.option(
    "--min-stratum-size-for-cap",
    default=1,
    show_default=True,
    type=int,
    help="Strata smaller than this are pooled into an overflow stratum.",
)
@click.option(
    "--use-blob-storage",
    is_flag=True,
    help="Read/write Parquet via blob storage instead of the local filesystem.",
)
@click.option(
    "--bucket",
    default="lynceus",
    show_default=True,
    help="Blob storage bucket name (used only with --use-blob-storage).",
)
def sample_candidates(
    input_glob: str,
    output_path: str,
    fingerprint_field: str,
    fingerprint_n_bits: int,
    property_fields: tuple[str, ...],
    n_projected_dims: int,
    projection_density: float,
    random_seed: int,
    n_quantiles_per_dim: int,
    cap_per_stratum: int,
    min_stratum_size_for_cap: int,
    use_blob_storage: bool,
    bucket: str,
) -> None:
    config = StratificationConfig(
        fingerprint_field=fingerprint_field,
        fingerprint_n_bits=fingerprint_n_bits,
        property_fields=property_fields,
        n_projected_dims=n_projected_dims,
        projection_density=projection_density,
        random_seed=random_seed,
        n_quantiles_per_dim=n_quantiles_per_dim,
        cap_per_stratum=cap_per_stratum,
        min_stratum_size_for_cap=min_stratum_size_for_cap,
    )

    blob_storage_settings = get_blob_storage_settings() if use_blob_storage else None
    conn = get_connection(blob_storage_settings)

    target_glob = _resolve_path(input_glob, blob_storage_settings, bucket)
    target_output = _resolve_path(output_path, blob_storage_settings, bucket)

    if not file_exists(conn, target_glob):
        raise click.ClickException(f"Input Parquet not found: {target_glob}")

    raw_table = conn.execute(
        f"SELECT * FROM read_parquet('{target_glob}')"
    ).to_arrow_table()
    model = fit_projection(raw_table, config)
    projected_table = project_batch(raw_table, model)

    conn.register("projected_table", projected_table)
    binner = fit_quantile_bins("projected_table", config, connection=conn)

    query = build_capped_sample_query("projected_table", binner, config)

    conn.execute(f"COPY ({query}) TO '{target_output}' (FORMAT PARQUET)")

    if not file_exists(conn, target_output):
        raise click.ClickException(
            f"COPY reported success but {target_output} is not readable back "
            "via read_parquet — write did not land"
        )

    row_count, n_strata = conn.execute(
        f"SELECT COUNT(*), COUNT(DISTINCT resolved_stratum_id) "
        f"FROM read_parquet('{target_output}')"
    ).fetchall()[0]

    if row_count == 0:
        if blob_storage_settings is None:
            Path(target_output).unlink(missing_ok=True)
        raise click.ClickException(
            f"No rows sampled from '{target_glob}'; refusing to leave an empty output."
        )

    click.echo(
        f"Sampled {row_count} rows across {n_strata} strata "
        f"(cap={config.cap_per_stratum}) -> {target_output}"
    )
