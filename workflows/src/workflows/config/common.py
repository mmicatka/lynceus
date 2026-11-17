# workflows/src/workflows/config/common.py


from pathlib import Path
from typing import Annotated, Any, TypeVar

import yaml
from pydantic import AfterValidator, BaseModel, ConfigDict, StringConstraints

EXTENSION_KEY_PREFIX = "x-"


class ConfigError(ValueError):
    pass


def _reject_dot_segments(value: str) -> str:
    if any(segment in {".", ".."} for segment in value.split("/")):
        raise ValueError("path segments '.' and '..' are not allowed")
    return value


ConfigSlug = Annotated[
    str,
    StringConstraints(strip_whitespace=True, pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$"),
]

StoragePrefix = Annotated[
    str,
    StringConstraints(strip_whitespace=True, pattern=r"^[^/]+(/[^/]+)*$"),
    AfterValidator(_reject_dot_segments),
]


class StrictModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


ModelT = TypeVar("ModelT", bound=StrictModel)


def _strip_extension_keys(raw: dict[Any, Any]) -> dict[Any, Any]:
    return {
        key: value
        for key, value in raw.items()
        if not (isinstance(key, str) and key.startswith(EXTENSION_KEY_PREFIX))
    }


def load_config(path: Path, model: type[ModelT]) -> ModelT:
    with path.open() as handle:
        raw = yaml.safe_load(handle)
    if not isinstance(raw, dict):
        raise ConfigError(
            f"{path}: expected a mapping at the top level, got {type(raw).__name__}"
        )
    return model.model_validate(_strip_extension_keys(raw))
