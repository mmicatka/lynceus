# workflows/src/workflows/config/candidates.py


from typing import Optional

from pydantic import Field, PositiveInt

from workflows.config.common import ConfigSlug, StrictModel


class CandidateConfig(StrictModel):
    name: ConfigSlug
    sub_sample: Optional[PositiveInt] = None
    feature_list: list[str] = Field(min_length=1)
