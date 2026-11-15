# workflows/src/workflows/config/base.py


from pathlib import Path
from typing import Annotated, TypeVar

import yaml
from pydantic import BaseModel, ConfigDict, StringConstraints

ConfigSlug = Annotated[
    str,
    StringConstraints(strip_whitespace=True, pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$"),
]


class StrictModel(BaseModel):
    model_config = ConfigDict(frozen=True)


ModelT = TypeVar("ModelT", bound=BaseModel)


def load_config(path: Path, model: type[ModelT]) -> ModelT:
    with path.open() as handle:
        return model.model_validate(yaml.safe_load(handle))
