# src/workflows/config/screen.py

from pydantic import ByteSize, Field

from workflows.config.base import StrictModel


class CandidatesConfig(StrictModel):
    initial_shard_size: ByteSize
    source_prefix: str
    parquet_prefix: str
    sources: list[str] = Field(min_length=1)


class ScreenConfig(StrictModel):
    name: str
    candidates: CandidatesConfig
