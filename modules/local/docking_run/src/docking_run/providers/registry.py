# modules/local/docking_run/src/docking_run/providers/registry.py

from typing import Any

from .provider import DockingProvider
from .vina_cpu import VinaCPUProvider
from .vina_gpu import VinaGPUProvider

_PROVIDERS: dict[str, type[DockingProvider]] = {
    "cpu": VinaCPUProvider,
    "gpu": VinaGPUProvider,
}


def get_provider(name: str, **kwargs: Any) -> DockingProvider:
    """Construct a DockingProvider by name ('cpu' or 'gpu').

    kwargs are forwarded to the provider's constructor; unknown kwargs
    will raise TypeError from the constructor itself, which is preferable
    to silently swallowing typos in provider-specific options.
    """
    try:
        provider_cls = _PROVIDERS[name]
    except KeyError:
        raise ValueError(
            f"Unknown docking provider: {name!r}. Options: {sorted(_PROVIDERS)}"
        ) from None
    return provider_cls(**kwargs)


def available_providers() -> list[str]:
    return sorted(_PROVIDERS)
