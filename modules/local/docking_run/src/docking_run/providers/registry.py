# modules/local/docking_run/src/docking_run/providers/registry.py

from typing import Any

from .provider import DockingProvider
from .unidock_gpu import UnidockGPUProvider
from .vina_cpu import VinaCPUProvider

_PROVIDERS: dict[str, type[DockingProvider]] = {
    "cpu": VinaCPUProvider,
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
