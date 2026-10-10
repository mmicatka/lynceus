# src/workflows/config/screen.py

from typing import Optional

from pydantic import Field, PositiveInt

from workflows.config.base import StrictModel


class CandidatesConfig(StrictModel):
    sources: list[str] = Field(min_length=1)
    sub_sample: Optional[PositiveInt]


class FilterConfig(StrictModel):
    features: list[str] = Field(min_length=1)


class ScreenConfig(StrictModel):
    name: str
    candidates: CandidatesConfig
    filter: FilterConfig
