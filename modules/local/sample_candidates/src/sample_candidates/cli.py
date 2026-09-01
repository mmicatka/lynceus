# modules/local/sample_candidates/src/sample_candidates/cli.py

from __future__ import annotations

import json
from pathlib import Path

import click
import duckdb
import pyarrow.parquet as pq
from lynceus_utils.storage.blob_storage import get_blob_storage_settings
from pyarrow.fs import FileSystem, FileType, LocalFileSystem, S3FileSystem

from sample_candidates.binning import QuantileBinner, fit_quantile_bins
from sample_candidates.config import StratificationConfig
from sample_candidates.projection import ProjectionModel, fit_projection, project_batch
from sample_candidates.sampling import build_capped_sample_query


def _resolve_filesystem(
    path: str, use_blob_storage: bool, bucket: str
) -> tuple[FileSystem, str]:
    if not use_blob_storage:
        return LocalFileSystem(), path

    blob_settings = get_blob_storage_settings()
    target_path = f"{bucket}/{path.lstrip('/')}"
    filesystem = S3FileSystem(
        access_key=blob_settings.access_key_id,
        secret_key=blob_settings.access_key,
        endpoint_override=blob_settings.endpoint,
        region=blob_settings.region,
        scheme="https" if blob_settings.use_ssl else "http",
    )
    return filesystem, target_path


def _path_exists(filesystem: FileSystem, path: str) -> bool:
    info = filesystem.get_file_info(path)
    return info.type != FileType.NotFound


def _require_exists(filesystem: FileSystem, path: str, description: str) -> None:
    if not _path_exists(filesystem, path):
        raise click.ClickException(f"{description} not found: {path}")


def _read_table(filesystem: FileSystem, path: str) -> "pq.Table":
    with filesystem.open_input_stream(path) as f:
        return pq.read_table(f)


def _write_table(filesystem: FileSystem, table: "pq.Table", path: str) -> None:
    parent = str(Path(path).parent)
    if parent not in (".", ""):
        filesystem.create_dir(parent, recursive=True)
    with filesystem.open_output_stream(path) as f:
        pq.write_table(table, f)


def _load_config(config_path: Path | None) -> StratificationConfig:
    if config_path is None:
        return StratificationConfig()

    if not config_path.exists():
        raise click.ClickException(f"Config file not found: {config_path}")

    return StratificationConfig(**json.loads(config_path.read_text()))


def _save_binner(binner: QuantileBinner, filesystem: FileSystem, path: str) -> None:
    payload = json.dumps(
        {
            "dim_edges": [list(edges) for edges in binner.dim_edges],
            "n_projected_dims": binner.n_projected_dims,
        },
        indent=2,
    ).encode("utf-8")

    parent = str(Path(path).parent)
    if parent not in (".", ""):
        filesystem.create_dir(parent, recursive=True)
    with filesystem.open_output_stream(path) as f:
        f.write(payload)


def _load_binner(filesystem: FileSystem, path: str) -> QuantileBinner:
    _require_exists(filesystem, path, "Bin edges file")

    with filesystem.open_input_stream(path) as f:
        data = json.loads(f.read().decode("utf-8"))

    return QuantileBinner(
        dim_edges=tuple(tuple(edges) for edges in data["dim_edges"]),
        n_projected_dims=data["n_projected_dims"],
    )


config_option = click.option(
    "--config",
    "config_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="Path to a local JSON file overriding StratificationConfig defaults.",
)

blob_storage_options = [
    click.option(
        "--use-blob-storage",
        is_flag=True,
        help="Read/write Parquet and model artifacts via blob storage instead of the local filesystem.",
    ),
    click.option(
        "--bucket",
        type=str,
        default="lynceus",
        show_default=True,
        help="Blob storage bucket name (used only with --use-blob-storage).",
    ),
]

skip_if_exists_option = click.option(
    "--skip-if-exists",
    is_flag=True,
    help="Skip this step if the output already exists.",
)


def with_blob_storage_options(fn):
    for option in reversed(blob_storage_options):
        fn = option(fn)
    return fn


@click.group()
def cli() -> None:
    pass


@cli.command("fit-projection")
@click.option(
    "--input",
    "input_path",
    required=True,
    type=str,
    help="Parquet file (or single shard) to fit the projection on. "
    "Should be a representative sample, not the full library.",
)
@click.option(
    "--model-out",
    required=True,
    type=str,
    help="Directory to write the fitted projection model to.",
)
@config_option
@with_blob_storage_options
@skip_if_exists_option
def fit_projection_cmd(
    input_path: str,
    model_out: str,
    config_path: Path | None,
    use_blob_storage: bool,
    bucket: str,
    skip_if_exists: bool,
) -> None:
    config = _load_config(config_path)
    filesystem, target_model_out = _resolve_filesystem(
        model_out, use_blob_storage, bucket
    )
    _, target_input = _resolve_filesystem(input_path, use_blob_storage, bucket)

    if skip_if_exists and _path_exists(filesystem, f"{target_model_out}/metadata.json"):
        click.echo(f"{target_model_out} already exists. Skipping.")
        return

    _require_exists(filesystem, target_input, "Input Parquet file")

    table = _read_table(filesystem, target_input)
    model = fit_projection(table, config)
    model.save(target_model_out, filesystem)

    click.echo(
        f"Fitted projection ({config.n_projected_dims} dims) -> {target_model_out}"
    )


@cli.command("apply-projection")
@click.option(
    "--input",
    "input_path",
    required=True,
    type=str,
    help="Parquet shard to project.",
)
@click.option(
    "--model",
    "model_path",
    required=True,
    type=str,
    help="Directory containing a fitted projection model (from fit-projection).",
)
@click.option(
    "--output",
    "output_path",
    required=True,
    type=str,
    help="Path to write the projected Parquet shard to.",
)
@with_blob_storage_options
@skip_if_exists_option
def apply_projection_cmd(
    input_path: str,
    model_path: str,
    output_path: str,
    use_blob_storage: bool,
    bucket: str,
    skip_if_exists: bool,
) -> None:
    filesystem, target_output = _resolve_filesystem(
        output_path, use_blob_storage, bucket
    )
    _, target_input = _resolve_filesystem(input_path, use_blob_storage, bucket)
    _, target_model = _resolve_filesystem(model_path, use_blob_storage, bucket)

    if skip_if_exists and _path_exists(filesystem, target_output):
        click.echo(f"{target_output} already exists. Skipping.")
        return

    _require_exists(filesystem, target_input, "Input Parquet file")

    model = ProjectionModel.load(target_model, filesystem)
    table = _read_table(filesystem, target_input)
    projected = project_batch(table, model)

    _write_table(filesystem, projected, target_output)

    click.echo(f"Projected {projected.num_rows} rows -> {target_output}")


@cli.command("fit-bins")
@click.option(
    "--input-glob",
    required=True,
    help="Parquet glob (local path or s3://...) of already-projected shards, "
    "read directly by DuckDB regardless of --use-blob-storage.",
)
@click.option(
    "--bins-out",
    required=True,
    type=str,
    help="Path to write the fitted quantile bin edges (JSON) to.",
)
@config_option
@with_blob_storage_options
@skip_if_exists_option
def fit_bins_cmd(
    input_glob: str,
    bins_out: str,
    config_path: Path | None,
    use_blob_storage: bool,
    bucket: str,
    skip_if_exists: bool,
) -> None:
    config = _load_config(config_path)
    filesystem, target_bins_out = _resolve_filesystem(
        bins_out, use_blob_storage, bucket
    )

    if skip_if_exists and _path_exists(filesystem, target_bins_out):
        click.echo(f"{target_bins_out} already exists. Skipping.")
        return

    binner = fit_quantile_bins(input_glob, config)
    _save_binner(binner, filesystem, target_bins_out)

    click.echo(
        f"Fitted {config.n_quantiles_per_dim}-quantile bins -> {target_bins_out}"
    )


@cli.command("sample")
@click.option(
    "--input-glob",
    required=True,
    help="Parquet glob (local path or s3://...) of already-projected shards, "
    "read directly by DuckDB regardless of --use-blob-storage.",
)
@click.option(
    "--bins",
    "bins_path",
    required=True,
    type=str,
    help="Path to fitted quantile bin edges (from fit-bins).",
)
@click.option(
    "--output",
    "output_path",
    required=True,
    type=str,
    help="Path to write the capped stratified sample (Parquet) to.",
)
@config_option
@with_blob_storage_options
@skip_if_exists_option
def sample_cmd(
    input_glob: str,
    bins_path: str,
    output_path: str,
    config_path: Path | None,
    use_blob_storage: bool,
    bucket: str,
    skip_if_exists: bool,
) -> None:
    config = _load_config(config_path)
    filesystem, target_output = _resolve_filesystem(
        output_path, use_blob_storage, bucket
    )
    _, target_bins = _resolve_filesystem(bins_path, use_blob_storage, bucket)

    if skip_if_exists and _path_exists(filesystem, target_output):
        click.echo(f"{target_output} already exists. Skipping.")
        return

    binner = _load_binner(filesystem, target_bins)

    query = build_capped_sample_query(input_glob, binner, config)

    conn = duckdb.connect()
    result = conn.execute(query).to_arrow_table()

    if result.num_rows == 0:
        raise click.ClickException(
            f"No rows sampled from '{input_glob}'; refusing to write empty output."
        )

    _write_table(filesystem, result, target_output)

    n_strata = len(set(result.column("resolved_stratum_id").to_pylist()))
    click.echo(
        f"Sampled {result.num_rows} rows across {n_strata} strata "
        f"(cap={config.cap_per_stratum}) -> {target_output}"
    )


@cli.command("run-all")
@click.option(
    "--fit-input",
    required=True,
    type=str,
    help="Parquet file (representative sample) to fit the projection and bins on.",
)
@click.option(
    "--apply-glob",
    required=True,
    help="Parquet glob of shards to project, bin, and sample from. "
    "May be the same data as --fit-input for small/medium datasets.",
)
@click.option(
    "--apply-inputs",
    multiple=True,
    type=str,
    help="Explicit list of shard paths to project individually. If omitted, "
    "--fit-input is projected and used directly (single-shard convenience path).",
)
@click.option(
    "--workdir",
    required=True,
    type=str,
    help="Directory to write intermediate model/bins/projected artifacts to.",
)
@click.option(
    "--output",
    "output_path",
    required=True,
    type=str,
    help="Path to write the final capped stratified sample (Parquet) to.",
)
@config_option
@with_blob_storage_options
@skip_if_exists_option
def run_all_cmd(
    fit_input: str,
    apply_glob: str,
    apply_inputs: tuple[str, ...],
    workdir: str,
    output_path: str,
    config_path: Path | None,
    use_blob_storage: bool,
    bucket: str,
    skip_if_exists: bool,
) -> None:
    config = _load_config(config_path)
    filesystem, target_output = _resolve_filesystem(
        output_path, use_blob_storage, bucket
    )
    _, target_workdir = _resolve_filesystem(workdir, use_blob_storage, bucket)
    _, target_fit_input = _resolve_filesystem(fit_input, use_blob_storage, bucket)

    if skip_if_exists and _path_exists(filesystem, target_output):
        click.echo(f"{target_output} already exists. Skipping.")
        return

    _require_exists(filesystem, target_fit_input, "Fit input Parquet file")

    model_dir = f"{target_workdir}/projection_model"
    fit_table = _read_table(filesystem, target_fit_input)
    model = fit_projection(fit_table, config)
    model.save(model_dir, filesystem)
    click.echo(f"[1/4] Fitted projection -> {model_dir}")

    projected_dir = f"{target_workdir}/projected"
    filesystem.create_dir(projected_dir, recursive=True)

    shards_to_project = apply_inputs if apply_inputs else (fit_input,)
    for shard_path in shards_to_project:
        _, target_shard = _resolve_filesystem(shard_path, use_blob_storage, bucket)
        _require_exists(filesystem, target_shard, "Shard Parquet file")

        shard_table = _read_table(filesystem, target_shard)
        projected = project_batch(shard_table, model)
        out_shard = f"{projected_dir}/{Path(shard_path).name}"
        _write_table(filesystem, projected, out_shard)
    click.echo(f"[2/4] Projected {len(shards_to_project)} shard(s) -> {projected_dir}")

    projected_glob = f"{projected_dir}/*.parquet"

    bins_path = f"{target_workdir}/bin_edges.json"
    binner = fit_quantile_bins(projected_glob, config)
    _save_binner(binner, filesystem, bins_path)
    click.echo(f"[3/4] Fitted quantile bins -> {bins_path}")

    query = build_capped_sample_query(projected_glob, binner, config)
    conn = duckdb.connect()
    result = conn.execute(query).to_arrow_table()

    if result.num_rows == 0:
        raise click.ClickException(
            f"No rows sampled from '{projected_glob}'; refusing to write empty output."
        )

    _write_table(filesystem, result, target_output)

    n_strata = len(set(result.column("resolved_stratum_id").to_pylist()))
    click.echo(
        f"[4/4] Sampled {result.num_rows} rows across {n_strata} strata "
        f"(cap={config.cap_per_stratum}) -> {target_output}"
    )


def main() -> None:
    cli(prog_name="stratify-sample")


if __name__ == "__main__":
    main()
