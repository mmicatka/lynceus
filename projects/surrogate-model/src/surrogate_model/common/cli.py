# projects/surrogate-model/src/surrogate_model/common/cli.py


from collections.abc import Callable
from typing import TypeVar

import click
from lynceus_core.features import MOLECULAR_FEATURES

from surrogate_model.common.model import DEFAULT_MODEL_TYPE, ModelType

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


def model_type_option(func: F) -> F:
    return click.option(
        "--model-type",
        "model_type",
        type=click.Choice(list(ModelType), case_sensitive=False),
        default=DEFAULT_MODEL_TYPE,
        show_default=True,
        callback=lambda _ctx, _param, value: ModelType(value.lower()),
        help="Surrogate model architecture to train.",
    )(func)
