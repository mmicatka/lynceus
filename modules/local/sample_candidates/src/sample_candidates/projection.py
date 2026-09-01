# modules/local/sample_candidates/src/sample_candidates/projection.py

from __future__ import annotations

import io
import json
from dataclasses import dataclass
from typing import cast

import numpy as np
import pyarrow as pa
from scipy import sparse
from sklearn.random_projection import SparseRandomProjection

from sample_candidates.config import StratificationConfig


@dataclass(frozen=True)
class PropertyNormalizationStats:
    field: str
    mean: float
    std: float

    def normalize(self, values: np.ndarray) -> np.ndarray:
        if self.std == 0.0:
            raise ValueError(
                f"Zero-variance property field '{self.field}' cannot be "
                "normalized; check upstream descriptor computation."
            )
        return (values - self.mean) / self.std


@dataclass(frozen=True)
class ProjectionModel:
    config: StratificationConfig
    transformer: SparseRandomProjection
    property_stats: tuple[PropertyNormalizationStats, ...]

    def property_stats_by_field(self) -> dict[str, PropertyNormalizationStats]:
        return {s.field: s for s in self.property_stats}

    def save(self, path: str, filesystem: pa.fs.FileSystem) -> None:
        components = self.transformer.components_
        if sparse.issparse(components):
            components = cast(sparse.spmatrix, components).toarray()  # type: ignore

        components_buffer = io.BytesIO()
        np.save(components_buffer, components)  # type: ignore

        metadata = {
            "config": self.config.model_dump(),
            "property_stats": [
                {"field": s.field, "mean": s.mean, "std": s.std}
                for s in self.property_stats
            ],
            "n_components": int(self.transformer.n_components_),
        }

        filesystem.create_dir(path, recursive=True)

        with filesystem.open_output_stream(f"{path}/components.npy") as f:
            f.write(components_buffer.getvalue())

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
        property_stats = tuple(
            PropertyNormalizationStats(field=s["field"], mean=s["mean"], std=s["std"])
            for s in metadata["property_stats"]
        )

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

        return cls(
            config=config, transformer=transformer, property_stats=property_stats
        )


def _stack_fingerprint_column(
    fp_column: pa.ChunkedArray, n_bits: int
) -> sparse.csr_matrix:
    fp_lists = fp_column.to_pylist()

    n_rows = len(fp_lists)
    dense = np.zeros((n_rows, n_bits), dtype=np.float32)

    for row_idx, bits in enumerate(fp_lists):
        if bits is None:
            raise ValueError(
                f"Null fingerprint at row {row_idx}; fingerprint step "
                "must run and succeed before stratification."
            )
        if len(bits) != n_bits:
            raise ValueError(
                f"Fingerprint at row {row_idx} has length {len(bits)}, "
                f"expected {n_bits}."
            )
        dense[row_idx] = bits

    return sparse.csr_matrix(dense)


def _build_property_matrix(
    table: pa.Table,
    property_fields: tuple[str, ...],
    stats: tuple[PropertyNormalizationStats, ...] | None,
) -> tuple[np.ndarray, tuple[PropertyNormalizationStats, ...]]:
    columns = []
    computed_stats: list[PropertyNormalizationStats] = []

    for i, field in enumerate(property_fields):
        if field not in table.column_names:
            raise ValueError(f"Property field '{field}' not present in table.")

        values = table.column(field).to_numpy(zero_copy_only=False).astype(np.float64)

        if np.isnan(values).any():
            raise ValueError(
                f"Property field '{field}' contains null/NaN values; "
                "descriptor computation must be complete before stratification."
            )

        if stats is None:
            field_stats = PropertyNormalizationStats(
                field=field, mean=float(values.mean()), std=float(values.std())
            )
        else:
            field_stats = stats[i]
            if field_stats.field != field:
                raise ValueError(
                    f"Stats field order mismatch: expected '{field}', "
                    f"got '{field_stats.field}'."
                )

        computed_stats.append(field_stats)
        columns.append(field_stats.normalize(values))

    return np.column_stack(columns), tuple(computed_stats)


def _combined_feature_matrix(
    table: pa.Table,
    config: StratificationConfig,
    property_stats: tuple[PropertyNormalizationStats, ...] | None,
) -> tuple[sparse.csr_matrix, tuple[PropertyNormalizationStats, ...]]:
    if config.fingerprint_field not in table.column_names:
        raise ValueError(
            f"Fingerprint field '{config.fingerprint_field}' not present in table."
        )

    fp_matrix = _stack_fingerprint_column(
        table.column(config.fingerprint_field), config.fingerprint_n_bits
    )
    property_matrix, resolved_stats = _build_property_matrix(
        table, config.property_fields, property_stats
    )

    combined = sparse.hstack(
        [fp_matrix, sparse.csr_matrix(property_matrix)], format="csr"
    )
    return combined, resolved_stats  # type: ignore


def fit_projection(table: pa.Table, config: StratificationConfig) -> ProjectionModel:
    combined, property_stats = _combined_feature_matrix(
        table, config, property_stats=None
    )

    transformer = SparseRandomProjection(
        n_components=config.n_projected_dims,
        density=config.projection_density,
        random_state=config.random_seed,
    )
    transformer.fit(combined)

    return ProjectionModel(
        config=config, transformer=transformer, property_stats=property_stats
    )


def project_batch(table: pa.Table, model: ProjectionModel) -> pa.Table:
    combined, _ = _combined_feature_matrix(
        table, model.config, property_stats=model.property_stats
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
