# workflows/src/workflows/config/base.py

from pathlib import Path
from typing import TypeVar

import yaml
from pydantic import BaseModel, ConfigDict


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


ModelT = TypeVar("ModelT", bound=BaseModel)


def load_config(path: Path, model: type[ModelT]) -> ModelT:
    with path.open() as handle:
        return model.model_validate(yaml.safe_load(handle))
