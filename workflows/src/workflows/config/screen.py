# src/workflows/config/screen.py

from pydantic import Field

from workflows.config.base import StrictModel


class CandidatesConfig(StrictModel):
    sources: list[str] = Field(min_length=1)
    target_total: int
    min_per_source: int


class ScreenConfig(StrictModel):
    name: str
    candidates: CandidatesConfig
