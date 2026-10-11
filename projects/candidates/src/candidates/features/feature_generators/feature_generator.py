# modules/local/generate_features/src/generate_features/feature_generators/feature_generator.py # noqa: E501

# feature_generator.py

from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np
import pyarrow as pa
from rdkit.Chem import Mol


@dataclass(frozen=True)
class FeatureChunk:
    values: np.ndarray
    valid: np.ndarray


class FeatureGenerator(ABC):
    name: str

    @abstractmethod
    def compute_batch(self, batch: list[Mol]) -> list[list[float] | None]: ...

    @abstractmethod
    def feature_field_name(self) -> str: ...

    @abstractmethod
    def feature_field_type(self) -> pa.DataType: ...

    @abstractmethod
    def placeholder_value(self) -> list[float]: ...

    def valid_field_name(self) -> str:
        return f"{self.feature_field_name()}_valid"

    def output_fields(self) -> list[tuple[str, pa.DataType]]:
        return [
            (self.feature_field_name(), self.feature_field_type()),
            (self.valid_field_name(), pa.bool_()),
        ]

    def generate_feature_chunk(self, mols: list[Mol | None]) -> FeatureChunk:
        placeholder = np.asarray(self.placeholder_value(), dtype=np.float32)
        values = np.tile(placeholder, (len(mols), 1))
        valid = np.zeros(len(mols), dtype=bool)
        indices = [index for index, mol in enumerate(mols) if mol is not None]
        if indices:
            computed = self.compute_batch([mols[index] for index in indices])
            for index, value in zip(indices, computed):
                if value is not None:
                    values[index] = value
                    valid[index] = True
        return FeatureChunk(values=values, valid=valid)

    def to_columns(self, chunks: list[FeatureChunk]) -> list[tuple[str, pa.Array]]:
        values = np.concatenate([chunk.values for chunk in chunks])
        valid = np.concatenate([chunk.valid for chunk in chunks])
        vectors = pa.FixedSizeListArray.from_arrays(
            pa.array(values.ravel()), values.shape[1]
        ).cast(self.feature_field_type())
        return [
            (self.feature_field_name(), vectors),
            (self.valid_field_name(), pa.array(valid, type=pa.bool_())),
        ]
