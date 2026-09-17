# modules/local/feature_generation/src/feature_generation/feature_generators/feature_generator.py # noqa: E501

from abc import ABC, abstractmethod
from typing import Any

import pyarrow as pa
from rdkit.Chem import Mol


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

    def failure_result(self) -> dict[str, Any]:
        return {
            self.feature_field_name(): self.placeholder_value(),
            self.valid_field_name(): False,
        }

    def generate_feature_batch(self, batch: list[Mol]) -> list[dict[str, Any]]:
        computed = self.compute_batch(batch)
        return [
            {self.feature_field_name(): value, self.valid_field_name(): True}
            if value is not None
            else self.failure_result()
            for value in computed
        ]
