# modules/local/sample_candidates/src/sample_candidates/cli.py

from __future__ import annotations

import logging
from pathlib import Path

import click
from lynceus_utils.duckdb import file_exists, get_connection
from lynceus_utils.storage import BlobStorageSettings, get_blob_storage_settings

from sample_candidates.binning import fit_quantile_bins
from sample_candidates.config import FeatureKind, FeatureSpec, StratificationConfig
from sample_candidates.projection import fit_projection, project_batch
from sample_candidates.sampling import build_capped_sample_query

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


class FeatureSpecParamType(click.ParamType):
    name = "field"

    def convert(self, value, param, ctx) -> FeatureSpec:
        parts = value.split(":")
        if len(parts) not in (2, 3):
            self.fail(
                f"'{value}' is not a valid field spec; expected "
                "NAME:KIND or NAME:KIND:REDUCED_DIMS (e.g. 'mw:scalar' or "
                "'morgan_fp:array:32')",
                param,
                ctx,
            )

        name, kind_str = parts[0], parts[1]
        if not name:
            self.fail(f"'{value}' has an empty field name", param, ctx)

        try:
            kind = FeatureKind(kind_str)
        except ValueError:
            valid = ", ".join(k.value for k in FeatureKind)
            self.fail(
                f"'{kind_str}' is not a valid kind in '{value}'; expected one of: {valid}",
                param,
                ctx,
            )

        reduced_dims: int | None = None
        if len(parts) == 3:
            try:
                reduced_dims = int(parts[2])
            except ValueError:
                self.fail(
                    f"'{parts[2]}' is not a valid integer reduced_dims in '{value}'",
                    param,
                    ctx,
                )
        elif kind is FeatureKind.ARRAY:
            self.fail(
                f"'{value}' is kind=array but is missing REDUCED_DIMS "
                "(e.g. 'morgan_fp:array:32')",
                param,
                ctx,
            )

        try:
            return FeatureSpec(name=name, kind=kind, reduced_dims=reduced_dims)
        except ValueError as exc:
            self.fail(str(exc), param, ctx)


FEATURE_SPEC = FeatureSpecParamType()


def _resolve_path(
    path: str, blob_storage_settings: BlobStorageSettings | None, bucket: str
) -> str:
    if blob_storage_settings is None:
        return path
    return f"s3://{bucket}/{path.lstrip('/')}"


@click.command()
@click.option(
    "--input",
    "input_path",
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
    "--field",
    "features",
    type=FEATURE_SPEC,
    multiple=True,
    default=(
        "morgan_fingerprint:array:32",
        "molecular_weight:scalar",
        "calculated_distribution_coefficient:scalar",
        "topological_polar_surface_area:scalar",
    ),
    show_default=True,
    help="Feature column to include, as NAME:KIND or NAME:KIND:REDUCED_DIMS. "
    "KIND is 'scalar' or 'array'. Array fields require "
    "REDUCED_DIMS (TruncatedSVD target dimensionality). Repeatable.",
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
    input_path: str,
    output_path: str,
    features: tuple[FeatureSpec, ...],
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
        features=features,
        n_projected_dims=n_projected_dims,
        projection_density=projection_density,
        random_seed=random_seed,
        n_quantiles_per_dim=n_quantiles_per_dim,
        cap_per_stratum=cap_per_stratum,
        min_stratum_size_for_cap=min_stratum_size_for_cap,
    )

    if use_blob_storage:
        blob_storage_settings = get_blob_storage_settings()
        conn = get_connection(blob_storage_settings)
        input_path = f"s3://{bucket}/{input_path.lstrip('/')}"
        output_path = f"s3://{bucket}/{output_path.lstrip('/')}"
    else:
        blob_storage_settings = None
        conn = get_connection()

    raw_table = conn.execute(
        f"SELECT * FROM read_parquet('{input_path}')"
    ).to_arrow_table()
    model = fit_projection(raw_table, config)
    projected_table = project_batch(raw_table, model)

    conn.register("projected_table", projected_table)
    binner = fit_quantile_bins("projected_table", config, connection=conn)

    query = build_capped_sample_query("projected_table", binner, config)

    conn.execute(f"COPY (SELECT * FROM ({query})) TO '{output_path}' (FORMAT PARQUET)")

    if not file_exists(conn, output_path):
        raise click.ClickException(
            f"COPY reported success but {output_path} is not readable back "
            "via read_parquet — write did not land"
        )

    row_count, n_strata = conn.execute(
        f"SELECT COUNT(*), COUNT(DISTINCT resolved_stratum_id) "
        f"FROM read_parquet('{output_path}')"
    ).fetchall()[0]

    if row_count == 0:
        if blob_storage_settings is None:
            Path(output_path).unlink(missing_ok=True)
        raise click.ClickException(
            f"No rows sampled from '{input_path}'; refusing to leave an empty output."
        )

    logger.info(
        "Sampled %d rows across %d strata (cap=%d) -> %s",
        row_count,
        n_strata,
        config.cap_per_stratum,
        output_path,
    )
