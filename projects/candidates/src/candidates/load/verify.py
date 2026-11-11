# projects/candidates/src/candidates/load/verify.py


from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import click

from candidates.load.common import (
    ShardLayout,
    leftover_staging_files,
    missing_final_shards,
    missing_staging_folders,
    unexpected_final_shards,
)

MAX_EXAMPLES = 5


@dataclass(frozen=True)
class Rule:
    description: str
    find_problems: Callable[[ShardLayout], list[str]]


CHECKS: dict[str, tuple[Rule, ...]] = {
    "final-shards-in-range": (
        Rule(
            "Final shard files outside the expected set (num_shards may have changed)",
            unexpected_final_shards,
        ),
    ),
    "staging-complete": (
        Rule("Staging is missing shard folders", missing_staging_folders),
    ),
    "merge-complete": (
        Rule("Final shards are missing", missing_final_shards),
        Rule("Staging still holds files", leftover_staging_files),
    ),
}


def _format_failure(rule: Rule, problems: list[str]) -> str:
    examples = ", ".join(problems[:MAX_EXAMPLES])
    return f"{rule.description}: {len(problems)} (e.g. {examples})"


def _run_check(check_name: str, layout: ShardLayout) -> list[str]:
    failures = []
    for rule in CHECKS[check_name]:
        problems = rule.find_problems(layout)
        if problems:
            failures.append(_format_failure(rule, problems))
    return failures


@click.command("verify_shard_layout")
@click.option("--check", "check_name", required=True, type=click.Choice(sorted(CHECKS)))
@click.option("--num-shards", required=True, type=click.IntRange(min=1))
@click.option(
    "--filename-template",
    required=True,
    help="Final shard filename with an {id} placeholder.",
)
@click.option(
    "--folder-prefix",
    required=True,
    help="Staging folder name prefix preceding the shard id.",
)
@click.option(
    "--shards-dir",
    required=True,
    type=click.Path(file_okay=False, path_type=Path),
)
@click.option(
    "--staging-dir",
    required=True,
    type=click.Path(file_okay=False, path_type=Path),
)
def verify_shard_layout(
    check_name: str,
    num_shards: int,
    filename_template: str,
    folder_prefix: str,
    shards_dir: Path,
    staging_dir: Path,
) -> None:
    layout = ShardLayout(
        num_shards=num_shards,
        filename_template=filename_template,
        folder_prefix=folder_prefix,
        shards_dir=shards_dir,
        staging_dir=staging_dir,
    )
    failures = _run_check(check_name, layout)
    if failures:
        raise click.ClickException("\n".join(failures))
    click.echo(f"Check {check_name!r} passed")
