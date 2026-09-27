# modules/local/surrogate_model/src/surrogate_model/sample_candidates.py

import heapq
import json
import os
import random
import tempfile
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import PurePosixPath

import click
import duckdb
import joblib
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from lynceus_utils import get_blob_storage_settings, get_connection, get_filesystem
from lynceus_utils.cli import NumWorkers
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


def _process_single_shard(
    shard_pair: tuple[str, str],
    id_column: str,
    feature_columns: list[str],
    model,
    top_k: int | None,
    uniform_k: int,
    seed: int,
    batch_size: int,
) -> tuple[list[tuple[float, dict]], list[tuple[float, dict]], int]:
    feature_path, conformer_path = shard_pair

    rng = random.Random(seed + hash(feature_path))
    local_con = duckdb.connect()

    local_active_heap: list[tuple[float, dict]] = []
    local_uniform_heap: list[
        tuple[float, dict]
    ] = []  # Changed to heap for easy merging
    rows_scanned = 0

    feature_schema_columns = local_con.sql(
        f"SELECT * FROM read_parquet('{feature_path}') LIMIT 0"
    ).columns
    conformer_schema_columns = local_con.sql(
        f"SELECT * FROM read_parquet('{conformer_path}') LIMIT 0"
    ).columns
    conformer_overlap = [
        c for c in conformer_schema_columns if c in feature_schema_columns
    ]
    exclude_clause = ", ".join(conformer_overlap) if conformer_overlap else id_column

    relation = local_con.sql(f"""
        SELECT f.*, c.* EXCLUDE ({exclude_clause}), c.{id_column} AS _conformer_id
        FROM read_parquet('{feature_path}') AS f
        LEFT JOIN read_parquet('{conformer_path}') AS c ON f.id = c.id
    """)

    reader = relation.fetch_arrow_reader(batch_size=batch_size)
    output_columns = [c for c in relation.columns if c != "_conformer_id"]

    for batch in reader:
        output_batch = batch.select(output_columns)
        batch_num_rows = batch.num_rows

        if model is not None:
            feature_frame = batch.select(feature_columns).to_pandas()
            scores = model.predict_proba(feature_frame)[:, 1]

            k_batch = min(top_k, batch_num_rows) if top_k else 0
            if k_batch > 0:
                top_indices = np.argpartition(scores, -k_batch)[-k_batch:]
                for idx in top_indices:
                    score = float(scores[idx])
                    if top_k and len(local_active_heap) < top_k:
                        row = output_batch.slice(int(idx), 1).to_pylist()[0]
                        heapq.heappush(local_active_heap, (score, row))
                    elif score > local_active_heap[0][0]:
                        row = output_batch.slice(int(idx), 1).to_pylist()[0]
                        heapq.heapreplace(local_active_heap, (score, row))

        for i in range(batch_num_rows):
            rand_val = rng.random()
            if len(local_uniform_heap) < uniform_k:
                row = output_batch.slice(i, 1).to_pylist()[0]
                heapq.heappush(local_uniform_heap, (rand_val, row))
            elif rand_val > local_uniform_heap[0][0]:
                row = output_batch.slice(i, 1).to_pylist()[0]
                heapq.heapreplace(local_uniform_heap, (rand_val, row))

        rows_scanned += batch_num_rows

    local_con.close()
    return local_active_heap, local_uniform_heap, rows_scanned


def _sample_candidates_parallel(
    shard_pairs: list[tuple[str, str]],
    id_column: str,
    feature_columns: list[str],
    model,
    top_k: int | None,
    uniform_k: int,
    seed: int,
    batch_size: int,
    max_workers: int,
) -> tuple[list[tuple[float, dict]], list[dict], int]:

    global_active_heap = []
    global_uniform_heap = []
    total_rows_scanned = 0
    total_shards = len(shard_pairs)

    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(
                _process_single_shard,
                shard_pair,
                id_column,
                feature_columns,
                model,
                top_k,
                uniform_k,
                seed,
                batch_size,
            )
            for shard_pair in shard_pairs
        ]

        for idx, future in enumerate(as_completed(futures), start=1):
            local_active, local_uniform, rows_scanned = future.result()
            total_rows_scanned += rows_scanned

            click.echo(
                f"sample_surrogate_candidates: finished shard {idx}/{total_shards} "
                f"({rows_scanned} rows in this shard)"
            )

            if top_k:
                for item in local_active:
                    if len(global_active_heap) < top_k:
                        heapq.heappush(global_active_heap, item)
                    elif item[0] > global_active_heap[0][0]:
                        heapq.heapreplace(global_active_heap, item)

            # Merge Uniform Random Heaps
            for item in local_uniform:
                if len(global_uniform_heap) < uniform_k:
                    heapq.heappush(global_uniform_heap, item)
                elif item[0] > global_uniform_heap[0][0]:
                    heapq.heapreplace(global_uniform_heap, item)

    final_reservoir = [row for _, row in global_uniform_heap]

    return global_active_heap, final_reservoir, total_rows_scanned


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
@click.option("--features", required=True)
@click.option("--conformers", required=True)
@click.option("--model-path", "model_key", default=None)
@click.option("--output", "output_key", required=True)
@click.option("--id-column", default="id", show_default=True)
@click.option("--top-k", type=int, default=None)
@click.option("--uniform-k", type=int, required=True)
@click.option("--seed", type=int, default=0, show_default=True)
@click.option("--batch-size", type=int, default=100_000, show_default=True)
@click.option("--use-blob-storage", is_flag=True, default=False)
@click.option("--bucket", default="lynceus", show_default=True)
@click.option(
    "--num-workers",
    default="auto",
    type=NumWorkers(),
    show_default=True,
    help="Number of parallel workers (integer >= 1 or 'auto').",
)
def sample_candidates(
    features: str,
    conformers: str,
    model_key: str | None,
    output_key: str,
    id_column: str,
    top_k: int | None,
    uniform_k: int,
    seed: int,
    batch_size: int,
    use_blob_storage: bool,
    bucket: str,
    num_workers: int,
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
    con = get_connection(blob_storage_settings, num_workers)

    output_path = _blob_path(use_blob_storage, bucket, output_key)
    model_path = (
        _blob_path(use_blob_storage, bucket, model_key)
        if model_key is not None
        else None
    )

    features_glob = f"{features.rstrip('/')}/*.parquet"
    conformers_glob = f"{conformers.rstrip('/')}/*.parquet"

    resolved_features_glob = _blob_path(use_blob_storage, bucket, features_glob)
    resolved_conformer_glob = _blob_path(use_blob_storage, bucket, conformers_glob)

    if _output_is_valid(filesystem, output_path, model_path, top_k, uniform_k):
        click.echo(
            f"sample_surrogate_candidates: valid output already at {output_path}"
        )
        return

    shard_pairs = _resolve_shard_pairs(
        filesystem, resolved_features_glob, resolved_conformer_glob
    )

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

    heap, reservoir, rows_scanned = _sample_candidates_parallel(
        shard_pairs=shard_pairs,
        id_column=id_column,
        feature_columns=feature_columns,
        model=model,
        top_k=top_k,
        uniform_k=uniform_k,
        seed=seed,
        batch_size=batch_size,
        max_workers=num_workers,  # Pass the CLI argument here
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
            f"sample_surrogate_candidates: wrote {uniform_k} uniform docking-input"
            f" rows ({rows_scanned} rows scanned) to {output_path}"
        )
