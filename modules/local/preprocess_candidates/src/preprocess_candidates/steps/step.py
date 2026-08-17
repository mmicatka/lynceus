# modules/local/preprocess_candidates/src/preprocess_candidates/steps/step.py

from dataclasses import dataclass, field
from typing import Any, Protocol

from rdkit import Chem


@dataclass
class StepContext:
    catalog_id: str
    smiles: str
    mol: Chem.Mol
    scratch: dict[str, Any] = field(default_factory=dict)


class Step(Protocol):
    name: str

    def init_worker(self) -> None: ...

    def compute(self, ctx: StepContext) -> dict[str, Any]: ...

    def failure_result(self) -> dict[str, Any]: ...

    def output_fields(self) -> list[tuple[str, Any]]: ...
