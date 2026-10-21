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


def label_definition_options(func: F) -> F:
    func = click.option(
        "--threshold",
        type=float,
        default=None,
        help="Affinity cutoff (kcal/mol) defining active. "
        "Mutually exclusive with --active-percentile.",
    )(func)
    return click.option(
        "--active-percentile",
        type=float,
        default=None,
        help="Active percentile. Mutually exclusive with --threshold.",
    )(func)


def require_single_label_definition(
    active_percentile: float | None, threshold: float | None
) -> None:
    if active_percentile is not None and threshold is not None:
        raise click.UsageError(
            "Illegal usage: --active-percentile and --threshold are mutually exclusive."
        )
    if active_percentile is None and threshold is None:
        raise click.UsageError(
            "You must specify exactly one of: --active-percentile OR --threshold."
        )
