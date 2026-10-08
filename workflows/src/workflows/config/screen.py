# src/workflows/config/screen.py

from typing import Optional

from pydantic import Field, PositiveInt

from workflows.config.base import StrictModel


class SubSampleConfig(StrictModel):
    candidates: PositiveInt
    shards: PositiveInt


class CandidatesConfig(StrictModel):
    sources: list[str] = Field(min_length=1)
    sub_sample: Optional[SubSampleConfig]


class ScreenConfig(StrictModel):
    name: str
    candidates: CandidatesConfig
