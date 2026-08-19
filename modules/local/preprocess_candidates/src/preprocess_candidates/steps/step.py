# modules/local/preprocess_candidates/src/preprocess_candidates/steps/step.py

from typing import Any, Protocol

from rdkit import Chem


class Step(Protocol):
    name: str

    def init_worker(self) -> None: ...

    def compute(self, mol: Chem.Mol) -> dict[str, Any]: ...

    def failure_result(self) -> dict[str, Any]: ...

    def output_fields(self) -> list[tuple[str, Any]]: ...
