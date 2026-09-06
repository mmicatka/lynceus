# modules/local/sample_candidates/src/sample_candidates/cli.py

from __future__ import annotations

import logging
from pathlib import Path

import click
from lynceus_utils.duckdb import file_exists, get_connection
from lynceus_utils.storage import get_blob_storage_settings, get_filesystem

from sample_candidates.autotune import suggest_stratification_shape
from sample_candidates.binning import fit_quantile_bins
from sample_candidates.config import FeatureKind, FeatureSpec, StratificationConfig
from sample_candidates.manifest import (
    build_entry,
    existing_entry_is_valid,
    load_manifest,
    manifest_path,
    serialize_params,
    write_manifest,
)
from sample_candidates.projection import fit_projection, project_batch
from sample_candidates.sampling import (
    build_capped_sample_query,
    resolve_cap_per_stratum,
)

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
                (
                    f"'{kind_str}' is not a valid kind in '{value}';"
                    f" expected one of: {valid}"
                ),
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


def _matched_input_files(con, input_path: str) -> list[str]:
    rows = con.execute(
        "SELECT DISTINCT filename FROM read_parquet(?, filename=true)",
        [input_path],
    ).fetchall()
    return sorted(row[0] for row in rows)


def _count_rows(con, input_path: str) -> int:
    result = con.execute(
        f"SELECT COUNT(*) FROM read_parquet('{input_path}')"
    ).fetchone()
    if result is None:
        raise click.ClickException(f"Could not count rows for '{input_path}'.")
    return result[0]


def _resolve_stratification_shape(
    con,
    input_path: str,
    *,
    n_projected_dims: int | None,
    n_quantiles_per_dim: int | None,
    target_total_samples: int | None,
    desired_cap_per_stratum: int,
) -> tuple[int, int]:
    if n_projected_dims is not None and n_quantiles_per_dim is not None:
        return n_projected_dims, n_quantiles_per_dim

    if target_total_samples is None:
        raise click.ClickException(
            "--n-projected-dims and --n-quantiles-per-dim must both be "
            "provided explicitly when using --cap-per-stratum; autotuning "
            "is only supported with --target-total-samples."
        )

    n_input_rows = _count_rows(con, input_path)
    shape = suggest_stratification_shape(
        n_input_rows=n_input_rows,
        target_total_samples=target_total_samples,
        n_quantiles_per_dim=n_quantiles_per_dim
        if n_quantiles_per_dim is not None
        else 10,
        desired_cap_per_stratum=desired_cap_per_stratum,
    )
    resolved_dims = (
        n_projected_dims if n_projected_dims is not None else shape.n_projected_dims
    )
    resolved_quantiles = (
        n_quantiles_per_dim
        if n_quantiles_per_dim is not None
        else shape.n_quantiles_per_dim
    )
    logger.info(
        "Autotuned stratification shape from %d input rows: "
        "n_projected_dims=%d n_quantiles_per_dim=%d (max n_strata=%d)",
        n_input_rows,
        resolved_dims,
        resolved_quantiles,
        shape.n_strata,
    )
    return resolved_dims, resolved_quantiles


@click.command()
@click.option(
    "--input",
    required=True,
    help="Parquet glob (local path or S3 prefix) of raw candidate shards"
    " to sample from.",
)
@click.option(
    "--output",
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
    default=None,
    type=int,
    help="Number of dimensions to random-project the combined feature vector into. "
    "If omitted and --target-total-samples is given, this is autotuned from "
    "the input row count.",
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
    default=None,
    type=int,
    help="Number of quantile bins per projected dimension. If omitted and "
    "--target-total-samples is given, this is autotuned from the input "
    "row count.",
)
@click.option(
    "--desired-cap-per-stratum",
    default=20,
    show_default=True,
    type=int,
    help="Only used when autotuning (--n-projected-dims/--n-quantiles-per-dim "
    "omitted with --target-total-samples): target average rows-per-stratum "
    "after capping, used to pick a stratification shape.",
)
@click.option(
    "--cap-per-stratum",
    default=None,
    type=int,
    help="Maximum number of rows drawn from any single stratum. Mutually "
    "exclusive with --target-total-samples; if neither is given, "
    "defaults to --cap-per-stratum 500.",
)
@click.option(
    "--target-total-samples",
    default=None,
    type=int,
    help="Target total output row count; cap_per_stratum is derived at "
    "runtime from the actual number of strata produced. Mutually "
    "exclusive with --cap-per-stratum.",
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
    input: str,
    output: str,
    features: tuple[FeatureSpec, ...],
    n_projected_dims: int | None,
    projection_density: float,
    random_seed: int,
    n_quantiles_per_dim: int | None,
    desired_cap_per_stratum: int,
    cap_per_stratum: int | None,
    target_total_samples: int | None,
    min_stratum_size_for_cap: int,
    use_blob_storage: bool,
    bucket: str,
) -> None:
    if cap_per_stratum is None and target_total_samples is None:
        cap_per_stratum = 500

    blob_storage_settings = None
    conn = get_connection()

    if use_blob_storage:
        blob_storage_settings = get_blob_storage_settings()
        conn = get_connection(blob_storage_settings)
        input = f"s3://{bucket}/{input.lstrip('/')}"
        output = f"s3://{bucket}/{output.lstrip('/')}"

    fs = get_filesystem(blob_storage_settings)

    matched_files = _matched_input_files(conn, input)
    if not matched_files:
        raise click.ClickException(
            f"Glob '{input}' matched no files — refusing to write an "
            f"empty manifest entry."
        )

    resolved_n_projected_dims, resolved_n_quantiles_per_dim = (
        _resolve_stratification_shape(
            conn,
            input,
            n_projected_dims=n_projected_dims,
            n_quantiles_per_dim=n_quantiles_per_dim,
            target_total_samples=target_total_samples,
            desired_cap_per_stratum=desired_cap_per_stratum,
        )
    )

    config = StratificationConfig(
        features=features,
        n_projected_dims=resolved_n_projected_dims,
        projection_density=projection_density,
        random_seed=random_seed,
        n_quantiles_per_dim=resolved_n_quantiles_per_dim,
        cap_per_stratum=cap_per_stratum,
        target_total_samples=target_total_samples,
        min_stratum_size_for_cap=min_stratum_size_for_cap,
    )

    manifest_file_path = manifest_path(output)
    manifest = load_manifest(fs, manifest_file_path)

    # cap_per_stratum is only known after n_strata is computed, so it is
    # excluded here; requested_params otherwise reflects every input that
    # can change sampling output, including the (possibly autotuned)
    # n_projected_dims/n_quantiles_per_dim actually used.
    requested_params = serialize_params(config, cap_per_stratum=None)

    existing_entry = manifest["globs"].get(input)
    if existing_entry is not None:
        recorded_params = dict(existing_entry.get("params") or {})
        recorded_cap = recorded_params.pop("cap_per_stratum", None)
        if recorded_params == requested_params:
            reconstructed_params = {**requested_params, "cap_per_stratum": recorded_cap}
            existing_entry_is_valid(
                conn, existing_entry, matched_files, reconstructed_params
            )
            logger.info(
                "Skipping '%s': already sampled (%d rows, %d strata, "
                "%d matched files unchanged) -> %s",
                input,
                existing_entry["row_count"],
                existing_entry["n_strata"],
                len(matched_files),
                existing_entry["output"],
            )
            return

    logger.info(
        "Sampling '%s' (%d files matched) -> %s", input, len(matched_files), output
    )

    raw_table = conn.execute(f"SELECT * FROM read_parquet('{input}')").to_arrow_table()
    model = fit_projection(raw_table, config)
    projected_table = project_batch(raw_table, model)

    conn.register("projected_table", projected_table)
    binner = fit_quantile_bins("projected_table", config, connection=conn)

    res = conn.execute(binner.count_strata_query("projected_table")).fetchone()

    if res:
        n_strata = res[0]
    else:
        raise click.ClickException(f"No strata available from '{input}'.")

    resolved_cap_per_stratum = resolve_cap_per_stratum(config, n_strata)
    query = build_capped_sample_query(
        "projected_table", binner, config, resolved_cap_per_stratum
    )

    conn.execute(f"COPY (SELECT * FROM ({query})) TO '{output}' (FORMAT PARQUET)")

    if not file_exists(conn, output):
        raise click.ClickException(
            f"COPY reported success but {output} is not readable back "
            "via read_parquet — write did not land"
        )

    row_count, n_strata = conn.execute(
        f"SELECT COUNT(*), COUNT(DISTINCT resolved_stratum_id) "
        f"FROM read_parquet('{output}')"
    ).fetchall()[0]

    if row_count == 0:
        if blob_storage_settings is None:
            Path(output).unlink(missing_ok=True)
        raise click.ClickException(
            f"No rows sampled from '{input}'; refusing to leave an empty output."
        )

    params = serialize_params(config, cap_per_stratum=resolved_cap_per_stratum)
    entry = build_entry(input, matched_files, output, params, row_count, n_strata)
    manifest["globs"][input] = entry
    write_manifest(fs, manifest_file_path, manifest)

    logger.info(
        "Sampled %d rows across %d strata (cap=%d) -> %s, updated manifest at %s",
        row_count,
        n_strata,
        resolved_cap_per_stratum,
        output,
        manifest_file_path,
    )
