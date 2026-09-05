# modules/local/sample_candidates/src/sample_candidates/projection.py

from __future__ import annotations

import io
import json
from dataclasses import dataclass
from typing import cast

import numpy as np
import pyarrow as pa
from scipy import sparse
from sklearn.decomposition import TruncatedSVD
from sklearn.random_projection import SparseRandomProjection

from sample_candidates.config import FeatureSpec, StratificationConfig


@dataclass(frozen=True)
class ScalarNormalizer:
    field: str
    mean: float
    std: float

    def normalize(self, values: np.ndarray) -> np.ndarray:
        if self.std == 0.0:
            raise ValueError(
                f"Zero-variance scalar field '{self.field}' cannot be "
                "normalized; check upstream descriptor computation."
            )
        return (values - self.mean) / self.std


@dataclass(frozen=True)
class ArrayReducer:
    field: str
    svd: TruncatedSVD
    component_means: np.ndarray
    component_stds: np.ndarray

    def transform(self, arr_matrix: sparse.csr_matrix) -> np.ndarray:
        reduced = self.svd.transform(arr_matrix)
        zero_std_mask = self.component_stds == 0.0
        if zero_std_mask.any():
            raise ValueError(
                f"Zero-variance SVD component(s) at index "
                f"{np.flatnonzero(zero_std_mask).tolist()} for field "
                f"'{self.field}'; array reducer was fit on degenerate data."
            )
        return (reduced - self.component_means) / self.component_stds

    @property
    def n_components(self) -> int:
        return int(self.svd.n_components)  # type: ignore[arg-type]


def _fit_array_reducer(
    field: str, arr_matrix: sparse.csr_matrix, n_components: int, random_seed: int
) -> tuple[ArrayReducer, np.ndarray]:
    svd = TruncatedSVD(n_components=n_components, random_state=random_seed)
    raw_reduced = svd.fit_transform(arr_matrix)

    component_means = raw_reduced.mean(axis=0)
    component_stds = raw_reduced.std(axis=0)

    reducer = ArrayReducer(
        field=field,
        svd=svd,
        component_means=component_means,
        component_stds=component_stds,
    )
    normalized = (raw_reduced - component_means) / np.where(
        component_stds == 0.0, 1.0, component_stds
    )
    return reducer, normalized


def _stack_array_column(arr_column: pa.ChunkedArray, field: str) -> sparse.csr_matrix:
    arr_lists = arr_column.to_pylist()

    n_rows = len(arr_lists)
    if n_rows == 0:
        raise ValueError(f"Fingerprint field '{field}' has no rows.")

    first_non_null = next((bits for bits in arr_lists if bits is not None), None)
    if first_non_null is None:
        raise ValueError(f"Fingerprint field '{field}' is entirely null.")
    n_bits = len(first_non_null)

    dense = np.zeros((n_rows, n_bits), dtype=np.float32)

    for row_idx, bits in enumerate(arr_lists):
        if bits is None:
            raise ValueError(
                f"Null array value at row {row_idx} in field '{field}'; "
                "array feature step must run and succeed before stratification."
            )
        if len(bits) != n_bits:
            raise ValueError(
                f"Fingerprint at row {row_idx} in field '{field}' has length "
                f"{len(bits)}, expected {n_bits}."
            )
        dense[row_idx] = bits

    return sparse.csr_matrix(dense)


def _build_scalar_matrix(
    table: pa.Table,
    scalar_features: tuple[FeatureSpec, ...],
    normalizers: dict[str, ScalarNormalizer] | None,
) -> tuple[np.ndarray, dict[str, ScalarNormalizer]]:
    columns = []
    resolved: dict[str, ScalarNormalizer] = {}

    for feature in scalar_features:
        field = feature.name
        if field not in table.column_names:
            raise ValueError(f"Scalar field '{field}' not present in table.")

        values = table.column(field).to_numpy(zero_copy_only=False).astype(np.float64)

        if np.isnan(values).any():
            raise ValueError(
                f"Scalar field '{field}' contains null/NaN values; "
                "descriptor computation must be complete before stratification."
            )

        if normalizers is None:
            normalizer = ScalarNormalizer(
                field=field, mean=float(values.mean()), std=float(values.std())
            )
        else:
            if field not in normalizers:
                raise ValueError(f"No fitted normalizer for scalar field '{field}'.")
            normalizer = normalizers[field]

        resolved[field] = normalizer
        columns.append(normalizer.normalize(values))

    return np.column_stack(columns), resolved


def _build_array_matrix(
    table: pa.Table,
    array_features: tuple[FeatureSpec, ...],
    reducers: dict[str, ArrayReducer] | None,
    random_seed: int,
) -> tuple[np.ndarray, dict[str, ArrayReducer]]:
    blocks = []
    resolved: dict[str, ArrayReducer] = {}

    for feature in array_features:
        field = feature.name
        if field not in table.column_names:
            raise ValueError(f"Fingerprint field '{field}' not present in table.")

        arr_matrix = _stack_array_column(table.column(field), field)

        if reducers is None:
            assert feature.reduced_dims is not None
            reducer, reduced = _fit_array_reducer(
                field, arr_matrix, feature.reduced_dims, random_seed
            )
        else:
            if field not in reducers:
                raise ValueError(f"No fitted reducer for array field '{field}'.")
            reducer = reducers[field]
            reduced = reducer.transform(arr_matrix)

        resolved[field] = reducer
        blocks.append(reduced)

    return np.hstack(blocks), resolved


@dataclass(frozen=True)
class ProjectionModel:
    config: StratificationConfig
    transformer: SparseRandomProjection
    scalar_normalizers: dict[str, ScalarNormalizer]
    array_reducers: dict[str, ArrayReducer]

    def save(self, path: str, filesystem: pa.fs.FileSystem) -> None:
        components = self.transformer.components_
        if sparse.issparse(components):
            components = cast(sparse.spmatrix, components).toarray()  # type: ignore

        components_buffer = io.BytesIO()
        np.save(components_buffer, components)  # type: ignore

        filesystem.create_dir(path, recursive=True)

        with filesystem.open_output_stream(f"{path}/components.npy") as f:
            f.write(components_buffer.getvalue())

        array_reducer_metadata = {}
        for field, reducer in self.array_reducers.items():
            svd_components_buffer = io.BytesIO()
            np.save(svd_components_buffer, reducer.svd.components_)
            with filesystem.open_output_stream(
                f"{path}/svd_components__{field}.npy"
            ) as f:
                f.write(svd_components_buffer.getvalue())

            array_reducer_metadata[field] = {
                "n_components": reducer.n_components,
                "component_means": reducer.component_means.tolist(),
                "component_stds": reducer.component_stds.tolist(),
                "explained_variance": reducer.svd.explained_variance_.tolist(),
                "singular_values": reducer.svd.singular_values_.tolist(),
            }

        metadata = {
            "config": self.config.model_dump(),
            "scalar_normalizers": {
                field: {"mean": n.mean, "std": n.std}
                for field, n in self.scalar_normalizers.items()
            },
            "array_reducers": array_reducer_metadata,
            "n_components": int(self.transformer.n_components_),
        }

        with filesystem.open_output_stream(f"{path}/metadata.json") as f:
            f.write(json.dumps(metadata, indent=2).encode("utf-8"))

    @classmethod
    def load(cls, path: str, filesystem: pa.fs.FileSystem) -> "ProjectionModel":
        metadata_path = f"{path}/metadata.json"
        components_path = f"{path}/components.npy"

        metadata_info = filesystem.get_file_info(metadata_path)
        components_info = filesystem.get_file_info(components_path)
        if (
            metadata_info.type == pa.fs.FileType.NotFound
            or components_info.type == pa.fs.FileType.NotFound
        ):
            raise ValueError(
                f"'{path}' does not contain a valid ProjectionModel "
                "(missing metadata.json or components.npy)."
            )

        with filesystem.open_input_stream(metadata_path) as f:
            metadata = json.loads(f.read().decode("utf-8"))
        config = StratificationConfig(**metadata["config"])

        scalar_normalizers = {
            field: ScalarNormalizer(field=field, mean=v["mean"], std=v["std"])
            for field, v in metadata["scalar_normalizers"].items()
        }

        with filesystem.open_input_stream(components_path) as f:
            components_buffer = io.BytesIO(f.read())
        components = np.load(components_buffer)

        transformer = SparseRandomProjection(
            n_components=config.n_projected_dims,
            density=config.projection_density,
            random_state=config.random_seed,
        )
        transformer.components_ = components
        transformer.n_components_ = metadata["n_components"]

        array_reducers: dict[str, ArrayReducer] = {}
        for field, meta in metadata["array_reducers"].items():
            svd_components_path = f"{path}/svd_components__{field}.npy"
            svd_components_info = filesystem.get_file_info(svd_components_path)
            if svd_components_info.type == pa.fs.FileType.NotFound:
                raise ValueError(
                    f"'{path}' is missing svd_components__{field}.npy referenced "
                    "in metadata.json."
                )
            with filesystem.open_input_stream(svd_components_path) as f:
                svd_components = np.load(io.BytesIO(f.read()))

            svd = TruncatedSVD(
                n_components=meta["n_components"], random_state=config.random_seed
            )
            svd.components_ = svd_components
            svd.explained_variance_ = np.array(meta["explained_variance"])
            svd.singular_values_ = np.array(meta["singular_values"])

            array_reducers[field] = ArrayReducer(
                field=field,
                svd=svd,
                component_means=np.array(meta["component_means"]),
                component_stds=np.array(meta["component_stds"]),
            )

        return cls(
            config=config,
            transformer=transformer,
            scalar_normalizers=scalar_normalizers,
            array_reducers=array_reducers,
        )


def _combined_feature_matrix(
    table: pa.Table,
    config: StratificationConfig,
    scalar_normalizers: dict[str, ScalarNormalizer] | None,
    array_reducers: dict[str, ArrayReducer] | None,
) -> tuple[np.ndarray, dict[str, ScalarNormalizer], dict[str, ArrayReducer]]:
    array_block, resolved_reducers = _build_array_matrix(
        table, config.array_features, array_reducers, config.random_seed
    )
    scalar_block, resolved_normalizers = _build_scalar_matrix(
        table, config.scalar_features, scalar_normalizers
    )

    combined = np.hstack([array_block, scalar_block])
    return combined, resolved_normalizers, resolved_reducers


def fit_projection(table: pa.Table, config: StratificationConfig) -> ProjectionModel:
    combined, scalar_normalizers, array_reducers = _combined_feature_matrix(
        table, config, scalar_normalizers=None, array_reducers=None
    )

    transformer = SparseRandomProjection(
        n_components=config.n_projected_dims,
        density=config.projection_density,
        random_state=config.random_seed,
    )
    transformer.fit(combined)

    return ProjectionModel(
        config=config,
        transformer=transformer,
        scalar_normalizers=scalar_normalizers,
        array_reducers=array_reducers,
    )


def project_batch(table: pa.Table, model: ProjectionModel) -> pa.Table:
    combined, _, _ = _combined_feature_matrix(
        table,
        model.config,
        scalar_normalizers=model.scalar_normalizers,
        array_reducers=model.array_reducers,
    )

    projected = model.transformer.transform(combined)
    if sparse.issparse(projected):
        projected = cast(sparse.spmatrix, projected).toarray()  # type: ignore

    projected_columns = {
        f"proj_dim_{i}": pa.array(projected[:, i], type=pa.float32())  # type: ignore
        for i in range(projected.shape[1])
    }

    result = table
    for name, arr in projected_columns.items():
        result = result.append_column(name, arr)

    return result
