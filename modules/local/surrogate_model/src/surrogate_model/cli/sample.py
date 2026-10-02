import click
import joblib
import numpy as np
import polars as pl
import pyarrow as pa
import pyarrow.parquet as pq
from lynceus_utils.duckdb import get_connection
from lynceus_utils.storage.blob_storage import get_blob_storage_settings
from lynceus_utils.storage.filesystem import get_filesystem, resolve_path

from surrogate_model.data import flatten_features, load_and_clean_data
from surrogate_model.model import ProbabilisticClassifier

STRATEGY_COLUMN = "_sample_strategy"
STRATEGY_UNIFORM = "uniform"
STRATEGY_TOP_K = "top_k"

RANDOM_SEED = 1000
FEATURE_COLS = [
    "atom_pair",
    "autocorr",
    "descriptors",
    "ecfp",
    "functional_groups",
    "morse",
    "rdf",
    "topological_torsion",
    "usrcat",
    "whim",
]


class TopKSelector:
    def __init__(self, k: int):
        self._k = k
        self._rows: pa.Table | None = None
        self._scores = np.empty(0, dtype=np.float64)

    def update(self, batch: pa.RecordBatch, scores: np.ndarray) -> None:
        if self._k <= 0 or batch.num_rows == 0:
            return

        scores = np.asarray(scores, dtype=np.float64)
        keep = _top_indices(scores, self._k)
        rows = pa.Table.from_batches([batch]).take(keep)
        scores = scores[keep]

        if self._rows is not None:
            rows = pa.concat_tables([self._rows, rows])
            scores = np.concatenate([self._scores, scores])
            keep = _top_indices(scores, self._k)
            rows, scores = rows.take(keep), scores[keep]

        self._rows, self._scores = rows, scores

    def result(self) -> pa.Table | None:
        if self._rows is None:
            return None
        # Sort by internal scores one last time before returning just the table
        order = np.argsort(-self._scores, kind="stable")
        return self._rows.take(order)


def _top_indices(scores: np.ndarray, k: int) -> np.ndarray:
    if len(scores) <= k:
        return np.arange(len(scores))
    return np.argpartition(scores, -k)[-k:]


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _parquet_columns(con, path: str) -> list[str]:
    return con.sql(f"SELECT * FROM read_parquet('{path}') LIMIT 0").columns


def _joined_query(con, feature_path: str, conformer_path: str, id_column: str) -> str:
    feature_schema = set(_parquet_columns(con, feature_path))
    excluded = [
        _quote(column)
        for column in _parquet_columns(con, conformer_path)
        if column in feature_schema or column == id_column
    ]
    join_key = _quote(id_column)
    return f"""
        SELECT f.*, c.* EXCLUDE ({", ".join(excluded)})
        FROM read_parquet('{feature_path}') AS f
        LEFT JOIN read_parquet('{conformer_path}') AS c
            ON f.{join_key} = c.{join_key}
    """


def _score_batch(
    model: ProbabilisticClassifier, feature_columns: list[str], batch: pa.RecordBatch
):
    df = pl.from_arrow(batch.select(feature_columns))
    df_clean = load_and_clean_data(df)
    x = flatten_features(df_clean, feature_cols=feature_columns)
    return model.predict_proba(x)[:, 1]


def _load_model(fs, model_path: str | None) -> object | None:
    if model_path is None:
        return None

    with fs.open(model_path, "rb") as f:
        model = joblib.load(f)

    return model


def _validate_sampling_options(model_path: str | None, top_k: int | None) -> None:
    if model_path is None and top_k is not None:
        raise click.UsageError(
            "sample_surrogate_candidates: --top-k has no effect without --model-path "
            "(there is no score to rank by); omit --top-k for a uniform-only sample"
        )
    if model_path is not None and top_k is None:
        raise click.UsageError(
            "sample_surrogate_candidates: --top-k is required when"
            " --model-path is given"
        )


def _annotate(rows: pa.Table, strategy: str) -> pa.Table:
    return rows.append_column(STRATEGY_COLUMN, pa.repeat(strategy, rows.num_rows))


def _dedupe_by_id(table: pa.Table, id_column: str) -> pa.Table:
    ids = table.column(id_column).to_numpy()
    _, first_occurrence = np.unique(ids, return_index=True)
    return table.take(np.sort(first_occurrence))


def _combine(
    uniform: pa.Table | None, active: pa.Table | None, id_column: str
) -> pa.Table | None:
    tables = [
        _annotate(rows, strategy)
        for strategy, rows in (
            (STRATEGY_UNIFORM, uniform),
            (STRATEGY_TOP_K, active),
        )
        if rows is not None
    ]
    if not tables:
        return None
    return _dedupe_by_id(pa.concat_tables(tables), id_column)


def _sample_shard(
    feature_path: str,
    conformer_path: str,
    id_column: str,
    model,
    feature_columns: list[str],
    top_k: int | None,
    uniform_k: int,
    seed: int,
    batch_size: int,
) -> tuple[pa.Table | None, int]:
    rng = np.random.default_rng(seed)
    uniform = TopKSelector(uniform_k)
    active = TopKSelector(top_k or 0)
    rows_scanned = 0

    con = get_connection()
    try:
        query = _joined_query(con, feature_path, conformer_path, id_column)
        for batch in con.sql(query).fetch_arrow_reader(batch_size=batch_size):
            uniform.update(batch, rng.random(batch.num_rows))
            if model is not None:
                active.update(batch, _score_batch(model, feature_columns, batch))
            rows_scanned += batch.num_rows
    finally:
        con.close()

    return _combine(uniform.result(), active.result(), id_column), rows_scanned


@click.command()
@click.option("--input-features", "features_path", required=True)
@click.option("--input-conformers", "conformers_path", required=True)
@click.option("--model-path", "model_path", default=None)
@click.option("--output", "output_path", required=True)
@click.option("--id-column", default="id", show_default=True)
@click.option(
    "--features",
    "-f",
    multiple=True,
    type=click.Choice(list(FEATURE_COLS), case_sensitive=False),
    default=list(FEATURE_COLS),
    show_default=True,
    help="Features to use.",
)
@click.option("--top-k", type=int, default=None)
@click.option("--uniform-k", type=int, required=True)
@click.option("--seed", type=int, default=RANDOM_SEED, show_default=True)
@click.option("--batch-size", type=int, default=100_000, show_default=True)
@click.option("--bucket", default="", show_default=True)
def sample_candidates(
    features_path: str,
    conformers_path: str,
    model_path: str | None,
    output_path: str,
    id_column: str,
    features: list[str],
    top_k: int | None,
    uniform_k: int,
    seed: int,
    batch_size: int,
    bucket: str,
):
    _validate_sampling_options(model_path, top_k)

    features_path = resolve_path(features_path, bucket)
    conformers_path = resolve_path(conformers_path, bucket)

    blob_storage_settings = get_blob_storage_settings() if bucket else None
    fs = get_filesystem(blob_storage_settings)
    model = _load_model(fs, model_path)

    click.echo(f"Sampling from {features_path} and {conformers_path}...")

    sampled, total_rows = _sample_shard(
        feature_path=features_path,
        conformer_path=conformers_path,
        id_column=id_column,
        model=model,
        feature_columns=features,
        top_k=top_k,
        uniform_k=uniform_k,
        seed=seed,
        batch_size=batch_size,
    )

    if sampled is None:
        click.echo("No candidates were sampled.")
        return

    with fs.open(output_path, "wb") as f:
        pq.write_table(sampled, f)

    click.echo(
        f"Successfully sampled {sampled.num_rows} candidates out of {total_rows}"
        f" scanned rows. Saved to {output_path}"
    )
