# modules/local/preprocess_candidates/src/preprocess_candidates/steps/pains.py

from typing import Any

import pyarrow as pa
from rdkit.Chem import Mol
from rdkit.Chem.FilterCatalog import FilterCatalog, FilterCatalogParams


class PainsStep:
    name = "basic_descriptors"

    def __init__(self) -> None:
        self._pains_catalog: FilterCatalog | None = None

    def init_worker(self) -> None:
        params = FilterCatalogParams()
        params.AddCatalog(FilterCatalogParams.FilterCatalogs.PAINS_A)
        params.AddCatalog(FilterCatalogParams.FilterCatalogs.PAINS_B)
        params.AddCatalog(FilterCatalogParams.FilterCatalogs.PAINS_C)

        self._pains_catalog = FilterCatalog(params)

    def compute(self, mol: Mol) -> dict[str, Any]:
        if self._pains_catalog is None:
            raise RuntimeError(
                f"{self.name}: init_worker() must be called before compute()"
            )

        matches = self._pains_catalog.GetMatches(mol)
        return {"pains": [m.GetDescription() for m in matches]}

    def failure_result(self) -> dict[str, Any]:
        return {
            "pains": [],
        }

    def output_fields(self) -> list[tuple[str, Any]]:
        return [
            ("pains", pa.list_(pa.string())),
        ]
