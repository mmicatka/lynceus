# modules/local/rebalance_candidates/src/rebalance_candidates/sample/sample_config.py

from pydantic import BaseModel


class FolderAllocation(BaseModel):
    folder: str
    source_count: int
    target_count: int


class SamplingPlan(BaseModel):
    target_total: int
    floor_per_folder: int
    allocations: list[FolderAllocation]

    def to_lookup(self) -> dict[str, int]:
        return {a.folder: a.target_count for a in self.allocations}
