# notebooks/metrics/surrogates/metrics/plots.py


from collections.abc import Sequence
from functools import partial
from typing import Mapping

import matplotlib.pyplot as plt
import numpy as np
import polars as pl
import seaborn as sns
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter, PercentFormatter


def plot_metric_trends(
    results: pl.DataFrame,
    metric_names: list[str],
    col_wrap: int = 3,
    height: float = 2.6,
    aspect: float = 1.3,
    ylim_bottom: float | None = 0.0,
):
    long = results.unpivot(
        metric_names, index=["run", "round"], variable_name="metric", value_name="value"
    ).to_pandas()
    rounds = sorted(results["round"].unique().to_list())

    with sns.axes_style("whitegrid"):
        grid = sns.relplot(
            data=long,
            x="round",
            y="value",
            hue="run",
            col="metric",
            col_order=metric_names,
            col_wrap=col_wrap,
            kind="line",
            marker="o",
            markersize=7,
            linewidth=2,
            palette="deep",
            height=height,
            aspect=aspect,
            facet_kws={"sharey": False, "sharex": True},
        )

    grid.set_titles("{col_name}")
    grid.set_axis_labels("round", "")
    grid.set(xticks=rounds)
    for ax in grid.axes.flat:
        ax.set_ylim(bottom=ylim_bottom)
        ax.margins(x=0.08)
    if grid.legend is not None and long["run"].nunique() == 1:
        grid.legend.remove()
    sns.despine(grid.figure)
    grid.figure.tight_layout()
    return grid


def plot_metric_groups(
    results: pl.DataFrame,
    groups: Mapping[str, Sequence[str]],
    panel_size: tuple[float, float] = (5.0, 3.8),
    ylim: tuple[float, float] = (0.0, 1.05),
) -> Figure:
    rounds = sorted(results["round"].unique().to_list())
    multiple_runs = results["run"].n_unique() > 1

    with sns.axes_style("whitegrid"):
        fig, axes = plt.subplots(
            1,
            len(groups),
            figsize=(panel_size[0] * len(groups), panel_size[1]),
            squeeze=False,
            layout="constrained",
        )

    for ax, (title, names) in zip(axes[0], groups.items()):
        long = results.unpivot(
            list(names),
            index=["run", "round"],
            variable_name="metric",
            value_name="value",
        ).to_pandas()
        plot = partial(
            sns.lineplot,
            data=long,
            x="round",
            y="value",
            hue="metric",
            hue_order=list(names),
            palette="deep",
            markersize=8,
            linewidth=2.2,
            ax=ax,
        )
        if multiple_runs:
            plot(style="run", markers=True)
        else:
            plot(marker="o")
        ax.set_title(title)
        ax.set_xlabel("round")
        ax.set_ylabel("")
        ax.set_xticks(rounds)
        ax.set_xlim(min(rounds) - 0.25, max(rounds) + 0.25)
        ax.set_ylim(*ylim)
        ax.set_yticks(np.linspace(0, 1, 6))
        ax.legend(
            title=None,
            frameon=False,
            loc="upper center",
            bbox_to_anchor=(0.5, -0.22),
            ncol=len(names),
        )
        sns.despine(ax=ax)

    plt.close(fig)
    return fig


def plot_gain_curves(
    curves: pl.DataFrame,
    ax: Axes | None = None,
    guide_fractions: tuple[float, ...] = (0.01, 0.05, 0.1),
) -> Figure:
    if ax is None:
        _, ax = plt.subplots(figsize=(8, 5), layout="constrained")

    frame = curves.to_pandas()
    rounds = sorted(curves["round"].unique().to_list())
    frame["round"] = frame["round"].astype(str)
    round_order = [str(r) for r in rounds]
    multiple_runs = frame["run"].nunique() > 1

    if len(rounds) >= 3:
        palette = (
            ["#312e81"]
            + sns.blend_palette(["#0f766e", "#14b8a6"], n_colors=len(rounds) - 2)
            + ["#10b981"]
        )
    else:
        palette = ["#312e81", "#10b981"][: len(rounds)]

    sns.lineplot(
        data=frame,
        x="fraction",
        y="recall",
        hue="round",
        hue_order=round_order,
        palette=palette,
        style="run" if multiple_runs else None,
        linewidth=2.2,
        alpha=0.88,
        ax=ax,
    )

    lines = ax.get_lines()
    if len(lines) >= len(rounds) and len(rounds) > 2:
        for line in lines[1 : len(rounds) - 1]:
            line.set_linewidth(1.4)
            line.set_alpha(0.45)
        lines[len(rounds) - 1].set_linewidth(2.6)
        lines[len(rounds) - 1].set_alpha(1.0)

    # True random baseline curved smoothly across the log x-axis
    lower = max(float(curves["fraction"].to_numpy().min()), 1e-4)
    x_rand = np.geomspace(lower, 1.0, 300)
    ax.plot(
        x_rand,
        x_rand,
        color="#94a3b8",
        linestyle=":",
        linewidth=1.5,
        label="random",
        zorder=1,
    )

    for fraction in guide_fractions:
        ax.axvline(fraction, color="#cbd5e1", linestyle="--", linewidth=0.9, zorder=0)
        ax.text(
            fraction,
            1.025,
            f"{fraction * 100:g}%",
            ha="center",
            va="bottom",
            fontsize=8.5,
            color="#64748b",
        )

    ax.set_xscale("log")
    ax.set_xlim(lower, 1)
    ax.set_ylim(0, 1.02)
    ax.xaxis.set_major_formatter(FuncFormatter(lambda x, _: f"{x * 100:g}%"))
    ax.yaxis.set_major_formatter(PercentFormatter(xmax=1, decimals=0))

    ax.set_xlabel(
        "library selected (log scale)", fontsize=10, color="#475569", labelpad=8
    )
    ax.set_ylabel("hits recovered", fontsize=10, color="#475569", labelpad=8)
    ax.set_title(
        "Cumulative recall by round", fontsize=12, fontweight="bold", loc="left", pad=18
    )

    ax.yaxis.grid(True, linestyle="--", linewidth=0.6, color="#e2e8f0", zorder=0)
    ax.spines["left"].set_color("#cbd5e1")
    ax.spines["bottom"].set_color("#cbd5e1")
    ax.tick_params(colors="#475569")

    ax.legend(
        title="round", frameon=False, loc="center left", bbox_to_anchor=(1.02, 0.5)
    )

    sns.despine(ax=ax)
    figure = ax.get_figure()
    if not isinstance(figure, Figure):
        raise TypeError(f"expected a Figure, got {type(figure).__name__}")
    plt.close(figure)
    return figure
