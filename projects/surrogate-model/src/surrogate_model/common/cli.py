# projects/surrogate-model/src/surrogate_model/common/cli.py


from collections.abc import Callable
from typing import TypeVar

import click
from lynceus_core.features import FEATURE_COLS

F = TypeVar("F", bound=Callable)


def features_option(func: F) -> F:
    return click.option(
        "--features",
        "-f",
        multiple=True,
        type=click.Choice(list(FEATURE_COLS), case_sensitive=False),
        default=list(FEATURE_COLS),
        show_default=True,
        help="Features to use, in the order the model was trained on.",
    )(func)
