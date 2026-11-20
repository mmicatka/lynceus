# projects/surrogate-model/src/surrogate_model/common/selection.py


from dataclasses import dataclass
from pathlib import Path

import numpy as np
import polars as pl
import pyarrow as pa
import pyarrow.parquet as pq

from surrogate_model.common.data import flatten_features
from surrogate_model.common.io import resolve_parquet_files, stream_tables
from surrogate_model.common.metrics import predict_active
from surrogate_model.common.model import ProbabilisticClassifier

VALID_SUFFIX = "_valid"
UNMODELED_SCORE = 0.0


@dataclass(frozen=True)
class SelectionParams:
    num_top: int
    num_random: int
    seed: int
    id_column: str
    batch_size: int


@dataclass(frozen=True)
class Selection:
    top: np.ndarray
    random: np.ndarray
    eligible_total: int
    remaining_total: int

    @property
    def positions(self) -> np.ndarray:
        return np.sort(np.concatenate([self.top, self.random]))


def id_column_type(file: str, id_column: str) -> pa.DataType:
    return pq.ParquetFile(file).schema_arrow.field(id_column).type


def exclusion_files(exclude_inputs: tuple[str, ...], output_path: str) -> list[str]:
    output = Path(output_path)
    return [
        file
        for pattern in exclude_inputs
        for file in resolve_parquet_files(pattern)
        if Path(file) != output
    ]


def load_excluded_ids(
    files: list[str], id_column: str, id_type: pa.DataType
) -> pa.Array | None:
    if not files:
        return None
    ids = (
        pa.concat_tables([pq.read_table(file, columns=[id_column]) for file in files])
        .column(id_column)
        .combine_chunks()
    )
    if ids.type != id_type:
        raise RuntimeError(
            f"Excluded id type {ids.type} does not match featurized id type {id_type}"
        )
    return ids


def _valid_columns(file: str) -> list[str]:
    return [
        name
        for name in pq.ParquetFile(file).schema_arrow.names
        if name.endswith(VALID_SUFFIX)
    ]


def _eligible_mask(
    chunk: pa.Table,
    valid_cols: list[str],
    id_column: str,
    excluded_ids: pa.Array | None,
) -> np.ndarray:
    mask = np.ones(chunk.num_rows, dtype=bool)
    if valid_cols:
        mask &= (
            pl.DataFrame(chunk.select(valid_cols))
            .select(pl.all_horizontal(valid_cols).fill_null(False))
            .to_series()
            .to_numpy()
        )
    if excluded_ids is not None:
        mask &= ~chunk.column(id_column).isin(excluded_ids).to_numpy()
    return mask


def _eligible_scores(
    model: ProbabilisticClassifier | None,
    chunk: pa.Table,
    eligible: np.ndarray,
    feature_cols: list[str],
) -> np.ndarray:
    if model is None:
        return np.full(int(eligible.sum()), UNMODELED_SCORE, dtype=np.float32)
    features = flatten_features(
        pl.DataFrame(chunk).filter(pl.Series(eligible)), feature_cols
    )
    return predict_active(model, features)


def _score_chunk(
    model: ProbabilisticClassifier | None,
    chunk: pa.Table,
    feature_cols: list[str],
    valid_cols: list[str],
    id_column: str,
    excluded_ids: pa.Array | None,
) -> np.ndarray:
    scores = np.full(chunk.num_rows, np.nan, dtype=np.float32)
    eligible = _eligible_mask(chunk, valid_cols, id_column, excluded_ids)
    if eligible.any():
        scores[eligible] = _eligible_scores(model, chunk, eligible, feature_cols)
    return scores


def _stream_columns(
    model: ProbabilisticClassifier | None,
    feature_cols: list[str],
    valid_cols: list[str],
    id_column: str,
) -> list[str]:
    modeled = feature_cols if model is not None else []
    return [id_column, *modeled, *valid_cols]


def _score_all(
    model: ProbabilisticClassifier | None,
    featurized_files: list[str],
    feature_cols: list[str],
    excluded_ids: pa.Array | None,
    total_rows: int,
    params: SelectionParams,
) -> np.ndarray:
    valid_cols = _valid_columns(featurized_files[0])
    columns = _stream_columns(model, feature_cols, valid_cols, params.id_column)
    scores = np.empty(total_rows, dtype=np.float32)
    offset = 0
    for chunk in stream_tables(featurized_files, columns, params.batch_size):
        end = offset + chunk.num_rows
        scores[offset:end] = _score_chunk(
            model, chunk, feature_cols, valid_cols, params.id_column, excluded_ids
        )
        offset = end
    return scores


def _select_top(scores: np.ndarray, num_top: int) -> tuple[np.ndarray, int]:
    scored_positions = np.flatnonzero(~np.isnan(scores))
    n_scored = len(scored_positions)
    k = min(num_top, n_scored)
    if k == 0:
        return np.empty(0, dtype=np.int64), n_scored
    if k == n_scored:
        return scored_positions, n_scored
    top = np.argpartition(scores[scored_positions], -k)[-k:]
    return np.sort(scored_positions[top]), n_scored


def _select_random(
    scores: np.ndarray,
    excluded: np.ndarray,
    num_random: int,
    rng: np.random.Generator,
) -> tuple[np.ndarray, int]:
    candidates = ~np.isnan(scores)
    candidates[excluded] = False
    remaining_positions = np.flatnonzero(candidates)
    k = min(num_random, len(remaining_positions))
    chosen = rng.choice(remaining_positions, size=k, replace=False)
    return np.sort(chosen), len(remaining_positions)


def select_positions(
    model: ProbabilisticClassifier | None,
    featurized_files: list[str],
    feature_cols: list[str],
    excluded_ids: pa.Array | None,
    total_rows: int,
    params: SelectionParams,
) -> Selection:
    scores = _score_all(
        model, featurized_files, feature_cols, excluded_ids, total_rows, params
    )
    rng = np.random.default_rng(params.seed)
    top, eligible_total = _select_top(scores, params.num_top)
    random, remaining_total = _select_random(scores, top, params.num_random, rng)
    return Selection(top, random, eligible_total, remaining_total)
