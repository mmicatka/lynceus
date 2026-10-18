# projects/lynceus-dock/src/lynceus_dock/__init__.py

import warnings

from .run_docking import run_docking

__all__ = ["run_docking"]


warnings.filterwarnings(
    "ignore",
    category=SyntaxWarning,
    module=r".*[/\\](prody|pyparsing)[/\\].*",
)
