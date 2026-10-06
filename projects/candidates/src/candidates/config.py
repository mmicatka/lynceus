# projects/candidates/src/candidates/allocate_candidates.py

from pydantic import BaseModel


class FolderAllocation(BaseModel):
    folder: str
    source_count: int
    target_count: int


class SubsetPlan(BaseModel):
    target_total: int
    min_per_folder: int
    allocations: list[FolderAllocation]

    def to_lookup(self) -> dict[str, int]:
        return {a.folder: a.target_count for a in self.allocations}
