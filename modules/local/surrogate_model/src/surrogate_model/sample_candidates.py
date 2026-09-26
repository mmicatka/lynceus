# modules/local/surrogate_model/src/surrogate_model/sample_candidates.py

# modules/local/surrogate_sampling/sample_surrogate_candidates.py

import heapq
import json
import os
import random
import tempfile
from pathlib import PurePosixPath

import click
import duckdb
import joblib
import pyarrow as pa
import pyarrow.parquet as pq
from lynceus_utils import get_blob_storage_settings, get_connection, get_filesystem
from lynceus_utils.storage import BlobStorageSettings


def _blob_path(use_blob_storage: bool, bucket: str, key: str) -> str:
    return f"s3://{bucket}/{key}" if use_blob_storage else key


def _output_is_valid(
    filesystem,
    output_path: str,
    model_path: str | None,
    top_k: int | None,
    uniform_k: int,
) -> bool:
    manifest_path = f"{output_path}.manifest.json"
    if not filesystem.exists(manifest_path) or not filesystem.exists(output_path):
        return False

    with filesystem.open(manifest_path, "r") as f:
        manifest = json.load(f)

    if manifest.get("model_path") != model_path:
        return False
    if manifest.get("top_k") != top_k:
        return False
    if manifest.get("uniform_k") != uniform_k:
        return False

    with filesystem.open(output_path, "rb") as f:
        table = pq.read_table(f)

    if model_path is None:
        uniform_count = table.filter(
            pa.compute.equal(table["bucket"], "uniform")
        ).num_rows
        return table.num_rows == uniform_count == uniform_k

    active_count = table.filter(pa.compute.equal(table["bucket"], "active")).num_rows
    uniform_count = table.filter(pa.compute.equal(table["bucket"], "uniform")).num_rows
    return active_count == top_k and uniform_count == uniform_k


def _write_manifest(
    filesystem,
    output_path: str,
    model_path: str | None,
    top_k: int | None,
    uniform_k: int,
    rows_scanned: int,
) -> None:
    manifest_path = f"{output_path}.manifest.json"
    manifest = {
        "model_path": model_path,
        "top_k": top_k,
        "uniform_k": uniform_k,
        "rows_scanned": rows_scanned,
    }
    with filesystem.open(manifest_path, "w") as f:
        json.dump(manifest, f)


def _resolve_shard_pairs(
    filesystem,
    features_glob: str,
    conformer_glob: str,
) -> list[tuple[str, str]]:
    feature_paths = sorted(filesystem.glob(features_glob))
    conformer_paths = sorted(filesystem.glob(conformer_glob))

    feature_by_name = {PurePosixPath(p).name: p for p in feature_paths}
    conformer_by_name = {PurePosixPath(p).name: p for p in conformer_paths}

    feature_names = set(feature_by_name)
    conformer_names = set(conformer_by_name)

    if feature_names != conformer_names:
        missing_conformers = feature_names - conformer_names
        missing_features = conformer_names - feature_names
        raise RuntimeError(
            "sample_surrogate_candidates: features/conformer shard sets do not "
            f"match. Feature shards with no conformer counterpart: "
            f"{sorted(missing_conformers)}. Conformer shards with no feature "
            f"counterpart: {sorted(missing_features)}"
        )

    if not feature_names:
        raise RuntimeError(
            f"sample_surrogate_candidates: no shards found for {features_glob}"
        )

    return [
        (feature_by_name[name], conformer_by_name[name])
        for name in sorted(feature_names)
    ]


def _reservoir_add(
    reservoir: list, reservoir_size: int, rows_scanned: int, row, rng: random.Random
) -> None:
    if len(reservoir) < reservoir_size:
        reservoir.append(row)
    else:
        j = rng.randint(0, rows_scanned)
        if j < reservoir_size:
            reservoir[j] = row


def _sample_candidates(
    con: duckdb.DuckDBPyConnection,
    shard_pairs: list[tuple[str, str]],
    id_column: str,
    feature_columns: list[str],
    model,
    top_k: int | None,
    uniform_k: int,
    seed: int,
    batch_size: int,
) -> tuple[list[tuple[float, dict]], list[dict], int]:
    rng = random.Random(seed)

    heap: list[tuple[float, dict]] = []
    reservoir: list[dict] = []
    rows_scanned = 0

    for feature_path, conformer_path in shard_pairs:
        # LEFT JOIN so a feature row with no matching conformer surfaces as
        # a NULL conformer id in the stream, rather than requiring a
        # separate full-shard count(*) pass to detect
        relation = con.sql(
            f"""
            SELECT f.*, c.* EXCLUDE ({id_column}), c.{id_column} AS _conformer_id
            FROM read_parquet('{feature_path}') AS f
            LEFT JOIN read_parquet('{conformer_path}') AS c
                ON f.{id_column} = c.{id_column}
            """
        )

        reader = relation.fetch_arrow_reader(batch_size=batch_size)

        for batch in reader:
            rows = batch.to_pylist()

            missing = [row[id_column] for row in rows if row["_conformer_id"] is None]
            if missing:
                raise RuntimeError(
                    f"sample_surrogate_candidates: {len(missing)} ids in "
                    f"{feature_path} have no matching conformer in "
                    f"{conformer_path} (e.g. {missing[:5]})"
                )

            for row in rows:
                del row["_conformer_id"]

            if model is not None:
                feature_batch = batch.select(feature_columns)
                feature_frame = feature_batch.to_pandas()
                scores = model.predict_proba(feature_frame)[:, 1]
            else:
                scores = [None] * len(rows)

            for row, score in zip(rows, scores):
                if score is not None:
                    score = float(score)
                    if top_k and len(heap) < top_k:
                        heapq.heappush(heap, (score, row))
                    elif score > heap[0][0]:
                        heapq.heapreplace(heap, (score, row))

                _reservoir_add(reservoir, uniform_k, rows_scanned, row, rng)
                rows_scanned += 1

    return heap, reservoir, rows_scanned


def _write_docking_input(
    filesystem,
    output_path: str,
    reservoir: list[dict],
    heap: list[tuple[float, dict]] | None,
) -> None:
    active_rows = [row for _, row in heap] if heap is not None else []
    uniform_rows = reservoir

    all_rows = []
    for row in active_rows:
        all_rows.append({**row, "bucket": "active"})
    for row in uniform_rows:
        all_rows.append({**row, "bucket": "uniform"})

    if not all_rows:
        raise RuntimeError(
            "sample_surrogate_candidates: no rows selected, nothing to write"
        )

    table = pa.Table.from_pylist(all_rows)

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = os.path.join(tmp_dir, "docking_input.parquet")
        pq.write_table(table, tmp_path, compression="zstd")

        with filesystem.open(output_path, "wb") as dst, open(tmp_path, "rb") as src:
            dst.write(src.read())


@click.command()
@click.option("--features-glob", required=True)
@click.option("--conformer-glob", required=True)
@click.option("--model-path", "model_key", default=None)
@click.option("--output", "output_key", required=True)
@click.option("--id-column", default="id", show_default=True)
@click.option("--top-k", type=int, default=None)
@click.option("--uniform-k", type=int, required=True)
@click.option("--seed", type=int, default=0, show_default=True)
@click.option("--batch-size", type=int, default=100_000, show_default=True)
@click.option("--use-blob-storage", is_flag=True, default=False)
@click.option("--bucket", default="lynceus", show_default=True)
def sample_candidates(
    features_glob: str,
    conformer_glob: str,
    model_key: str | None,
    output_key: str,
    id_column: str,
    top_k: int | None,
    uniform_k: int,
    seed: int,
    batch_size: int,
    use_blob_storage: bool,
    bucket: str,
):
    if model_key is None and top_k is not None:
        raise click.UsageError(
            "sample_surrogate_candidates: --top-k has no effect without --model-path "
            "(there is no score to rank by); omit --top-k for a uniform-only sample"
        )
    if model_key is not None and top_k is None:
        raise click.UsageError(
            "sample_surrogate_candidates: --top-k is required when"
            " --model-path is given"
        )

    blob_storage_settings: BlobStorageSettings | None = (
        get_blob_storage_settings() if use_blob_storage else None
    )
    filesystem = get_filesystem(blob_storage_settings)
    con = get_connection(blob_storage_settings)

    output_path = _blob_path(use_blob_storage, bucket, output_key)
    model_path = (
        _blob_path(use_blob_storage, bucket, model_key)
        if model_key is not None
        else None
    )
    resolved_features_glob = _blob_path(use_blob_storage, bucket, features_glob)
    resolved_conformer_glob = _blob_path(use_blob_storage, bucket, conformer_glob)

    if _output_is_valid(filesystem, output_path, model_path, top_k, uniform_k):
        click.echo(
            f"sample_surrogate_candidates: valid output already at {output_path},"
            " skipping"
        )
        return

    shard_pairs = _resolve_shard_pairs(
        filesystem, resolved_features_glob, resolved_conformer_glob
    )

    # schema is assumed identical across all feature shards; taken once
    # from the first shard rather than re-derived per shard
    first_feature_path, _ = shard_pairs[0]
    feature_columns = [
        c
        for c in con.sql(f"SELECT * FROM read_parquet('{first_feature_path}')").columns
        if c != id_column
    ]

    model = None
    if model_path is not None:
        with filesystem.open(model_path, "rb") as f:
            model = joblib.load(f)

    heap, reservoir, rows_scanned = _sample_candidates(
        con=con,
        shard_pairs=shard_pairs,
        id_column=id_column,
        feature_columns=feature_columns,
        model=model,
        top_k=top_k,
        uniform_k=uniform_k,
        seed=seed,
        batch_size=batch_size,
    )

    if model is not None and top_k and len(heap) < top_k:
        raise RuntimeError(
            f"sample_surrogate_candidates: only {len(heap)} rows scanned, "
            f"cannot satisfy top_k={top_k}"
        )
    if len(reservoir) < uniform_k:
        raise RuntimeError(
            f"sample_surrogate_candidates: only {len(reservoir)} rows scanned, "
            f"cannot satisfy uniform_k={uniform_k}"
        )

    _write_docking_input(filesystem, output_path, reservoir, heap=heap)
    _write_manifest(filesystem, output_path, model_path, top_k, uniform_k, rows_scanned)

    if model is not None:
        click.echo(
            f"sample_surrogate_candidates: wrote {top_k} active + {uniform_k} uniform "
            f"docking-input rows ({rows_scanned} rows scanned) to {output_path}"
        )
    else:
        click.echo(
            f"sample_surrogate_candidates: wrote {uniform_k} uniform docking-input rows "
            f"({rows_scanned} rows scanned) to {output_path}"
        )
