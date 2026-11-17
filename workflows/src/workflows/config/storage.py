# workflows/src/workflows/config/storage.py


from collections import Counter
from typing import Self

from pydantic import model_validator

from workflows.config.common import StoragePrefix, StrictModel

_BASE_FIELD = "base"


class PrefixGroup(StrictModel):
    def leaf_prefixes(self) -> tuple[str, ...]:
        leaves: list[str] = []
        for name in type(self).model_fields:
            value = getattr(self, name)
            if isinstance(value, PrefixGroup):
                leaves.extend(value.leaf_prefixes())
            elif name != _BASE_FIELD:
                leaves.append(value)
        return tuple(leaves)

    @model_validator(mode="after")
    def _require_unique_prefixes(self) -> Self:
        duplicates = sorted(
            prefix
            for prefix, count in Counter(self.leaf_prefixes()).items()
            if count > 1
        )
        if duplicates:
            raise ValueError(
                f"sibling prefixes must be unique, duplicated: {duplicates}"
            )
        return self


class BasedPrefixGroup(PrefixGroup):
    base: StoragePrefix
