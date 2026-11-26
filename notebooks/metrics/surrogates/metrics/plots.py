# notebooks/metrics/surrogates/metrics/plots.py


from collections.abc import Sequence
from dataclasses import dataclass

import matplotlib.pyplot as plt
import numpy as np
import polars as pl
import seaborn as sns
from matplotlib.axes import Axes
from matplotlib.colors import to_hex
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter, PercentFormatter

from .common import BEDROC_PREFIX, fraction_label

LINE_PALETTE = ("#0f766e", "#14b8a6", "#f59e0b", "#2563eb", "#7c3aed", "#e11d48")
ROUND_FIRST = "#312e81"
ROUND_MIDDLE = ("#0f766e", "#14b8a6")
ROUND_LAST = "#10b981"
RUN_LINESTYLES = ("-", "--", "-.", ":")
INK = "#0f172a"
MUTED = "#475569"
SPINE = "#cbd5e1"
GRID = "#e2e8f0"
GUIDE_TEXT = "#64748b"
BASELINE = "#94a3b8"
MIN_CURVE_FRACTION = 1e-4


@dataclass(frozen=True)
class MetricLine:
    key: str
    label: str | None = None
    color: str | None = None


@dataclass(frozen=True)
class Panel:
    title: str
    lines: Sequence[MetricLine | str]


@dataclass(frozen=True)
class RoundStyle:
    color: str
    linewidth: float
    alpha: float


def fraction_lines(prefix: str, fractions: Sequence[float]) -> list[MetricLine]:
    return [
        MetricLine(
            key=f"{prefix}@{fraction_label(fraction)}",
            label=f"{prefix.capitalize()}@{fraction_label(fraction)}",
        )
        for fraction in fractions
    ]


def bedroc_lines(results: pl.DataFrame) -> list[MetricLine]:
    return [
        MetricLine(key=column)
        for column in results.columns
        if column.startswith(BEDROC_PREFIX)
    ]


def _as_line(item: MetricLine | str) -> MetricLine:
    return item if isinstance(item, MetricLine) else MetricLine(key=item)


def _resolve_run(results: pl.DataFrame, run: str | None) -> str:
    if run is not None:
        return run
    runs = results["run"].unique().to_list()
    if len(runs) != 1:
        raise ValueError(f"multiple runs in results, pass run=...: {runs}")
    return runs[0]


def _style_axes(
    ax: Axes,
    title: str,
    xlabel: str,
    ylabel: str | None = None,
    title_pad: float = 14.0,
) -> None:
    ax.set_title(
        title, fontsize=12, fontweight="bold", loc="left", pad=title_pad, color=INK
    )
    ax.set_xlabel(xlabel, fontsize=10, color=MUTED, labelpad=8)
    if ylabel is not None:
        ax.set_ylabel(ylabel, fontsize=10, color=MUTED, labelpad=8)
    sns.despine(ax=ax)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(SPINE)
    ax.yaxis.grid(True, linestyle="--", linewidth=0.7, color=GRID, zorder=0)
    ax.xaxis.grid(False)
    ax.set_axisbelow(True)
    ax.tick_params(colors=MUTED, labelsize=9.5)


def _close(figure: Figure) -> Figure:
    plt.close(figure)
    return figure


def _figure_of(ax: Axes) -> Figure:
    figure = ax.get_figure()
    if not isinstance(figure, Figure):
        raise TypeError(f"expected a Figure, got {type(figure).__name__}")
    return figure


def _spread(values: Sequence[float], min_gap: float) -> list[float]:
    order = np.argsort(values)
    placed = np.asarray(values, dtype=float)[order]
    for index in range(1, placed.size):
        placed[index] = max(placed[index], placed[index - 1] + min_gap)
    result = np.empty_like(placed)
    result[order] = placed
    return result.tolist()


def _draw_panel(
    ax: Axes,
    panel: Panel,
    frame: pl.DataFrame,
    rounds: np.ndarray,
    ylim: tuple[float, float],
    min_label_gap: float,
) -> None:
    lines = [_as_line(item) for item in panel.lines]
    missing = [line.key for line in lines if line.key not in frame.columns]
    if missing:
        raise KeyError(f"metrics not in results: {missing}")

    values = [frame[line.key].to_numpy() for line in lines]
    colors = [
        line.color or LINE_PALETTE[index % len(LINE_PALETTE)]
        for index, line in enumerate(lines)
    ]
    for series, color in zip(values, colors):
        ax.plot(
            rounds,
            series,
            color=color,
            linewidth=2.4,
            marker="o",
            markersize=6.5,
            markerfacecolor="white",
            markeredgewidth=2.2,
            zorder=3,
        )

    finals = [float(series[-1]) for series in values]
    label_positions = _spread(finals, min_label_gap)
    for line, color, final, y in zip(lines, colors, finals, label_positions):
        ax.annotate(
            f"{line.label or line.key} ({final:.2f})",
            xy=(rounds[-1], y),
            xytext=(8, 0),
            textcoords="offset points",
            va="center",
            fontsize=9,
            fontweight="medium",
            color=color,
        )

    _style_axes(ax, panel.title, "Round")
    ax.set_xticks(rounds)
    ax.set_xlim(rounds.min() - 0.15, rounds.max() + 0.15)
    ax.set_ylim(*ylim)


def plot_metric_panels(
    results: pl.DataFrame,
    panels: Sequence[Panel],
    run: str | None = None,
    panel_width: float = 5.5,
    height: float = 4.4,
    wspace: float = 0.55,
    right_margin: float = 0.9,
    dpi: int = 150,
    ylim: tuple[float, float] = (0.0, 1.05),
    min_label_gap: float = 0.045,
) -> Figure:
    frame = results.filter(pl.col("run") == _resolve_run(results, run)).sort("round")
    rounds = frame["round"].to_numpy()

    fig, axes = plt.subplots(
        1,
        len(panels),
        figsize=(panel_width * len(panels), height),
        dpi=dpi,
        squeeze=False,
        gridspec_kw={"wspace": wspace},
    )
    fig.subplots_adjust(right=right_margin)
    for ax, panel in zip(axes[0], panels):
        _draw_panel(ax, panel, frame, rounds, ylim, min_label_gap)
    return _close(fig)


def _round_colors(count: int) -> list[str]:
    if count <= 2:
        return [ROUND_FIRST, ROUND_LAST][:count]
    middle = sns.blend_palette(ROUND_MIDDLE, n_colors=count - 2)
    return [ROUND_FIRST, *(to_hex(color) for color in middle), ROUND_LAST]


def _round_styles(rounds: Sequence[int]) -> dict[int, RoundStyle]:
    last = len(rounds) - 1
    styles: dict[int, RoundStyle] = {}
    for position, (round_index, color) in enumerate(
        zip(rounds, _round_colors(len(rounds)))
    ):
        if position == last:
            styles[round_index] = RoundStyle(color, 2.6, 1.0)
        elif position == 0:
            styles[round_index] = RoundStyle(color, 2.2, 0.88)
        else:
            styles[round_index] = RoundStyle(color, 1.4, 0.45)
    return styles


def _curve_label(run: str, round_index: int, multiple_runs: bool) -> str:
    return f"{run} / {round_index}" if multiple_runs else str(round_index)


def plot_gain_curves(
    curves: pl.DataFrame,
    ax: Axes | None = None,
    guide_fractions: Sequence[float] = (0.01, 0.05, 0.1),
) -> Figure:
    if ax is None:
        _, ax = plt.subplots(figsize=(8, 5), layout="constrained")

    runs = curves["run"].unique(maintain_order=True).to_list()
    rounds = sorted(curves["round"].unique().to_list())
    styles = _round_styles(rounds)
    lower = max(float(curves["fraction"].to_numpy().min()), MIN_CURVE_FRACTION)

    for run_index, run in enumerate(runs):
        linestyle = RUN_LINESTYLES[run_index % len(RUN_LINESTYLES)]
        for round_index in rounds:
            subset = curves.filter(
                (pl.col("run") == run) & (pl.col("round") == round_index)
            )
            if subset.is_empty():
                continue
            style = styles[round_index]
            ax.plot(
                subset["fraction"].to_numpy(),
                subset["recall"].to_numpy(),
                color=style.color,
                linewidth=style.linewidth,
                alpha=style.alpha,
                linestyle=linestyle,
                label=_curve_label(run, round_index, len(runs) > 1),
            )

    baseline = np.geomspace(lower, 1.0, 300)
    ax.plot(
        baseline,
        baseline,
        color=BASELINE,
        linestyle=":",
        linewidth=1.5,
        label="random",
        zorder=1,
    )

    for fraction in guide_fractions:
        ax.axvline(fraction, color=SPINE, linestyle="--", linewidth=0.9, zorder=0)
        ax.text(
            fraction,
            1.025,
            fraction_label(fraction),
            ha="center",
            va="bottom",
            fontsize=8.5,
            color=GUIDE_TEXT,
        )

    ax.set_xscale("log")
    ax.set_xlim(lower, 1)
    ax.set_ylim(0, 1.02)
    ax.xaxis.set_major_formatter(FuncFormatter(lambda value, _: fraction_label(value)))
    ax.yaxis.set_major_formatter(PercentFormatter(xmax=1, decimals=0))
    _style_axes(
        ax,
        "Cumulative recall by round",
        "library selected (log scale)",
        "hits recovered",
        title_pad=18.0,
    )
    ax.legend(
        title="round", frameon=False, loc="center left", bbox_to_anchor=(1.02, 0.5)
    )
    return _close(_figure_of(ax))
