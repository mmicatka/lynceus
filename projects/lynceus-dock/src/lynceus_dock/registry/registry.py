# projects/lynceus-dock/src/lynceus_dock/providers/registry.py

from typing import Any

from lynceus_dock.registry.common import DockingProvider
from lynceus_dock.registry.unidock_gpu import UnidockGPUProvider

_PROVIDERS: dict[str, type[DockingProvider]] = {
    "gpu": UnidockGPUProvider,
}


def get_provider(name: str, **kwargs: Any) -> DockingProvider:
    try:
        provider_cls = _PROVIDERS[name]
    except KeyError:
        raise ValueError(
            f"Unknown docking provider: {name!r}. Options: {sorted(_PROVIDERS)}"
        ) from None
    return provider_cls(**kwargs)


def available_providers() -> list[str]:
    return sorted(_PROVIDERS)
