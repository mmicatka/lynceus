# projects/surrogate-model/src/surrogate_model/common/cli.py


from collections.abc import Callable
from typing import TypeVar

import click
from lynceus_core.features import MOLECULAR_FEATURES

F = TypeVar("F", bound=Callable)


def features_option(func: F) -> F:
    return click.option(
        "--features",
        "-f",
        multiple=True,
        type=click.Choice(list(MOLECULAR_FEATURES), case_sensitive=False),
        default=list(MOLECULAR_FEATURES),
        show_default=True,
        help="Features to use, in the order the model was trained on.",
    )(func)
