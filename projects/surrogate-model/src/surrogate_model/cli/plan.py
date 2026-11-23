# projects/surrogate-model/src/surrogate_model/cli/plan.py


import json
from pathlib import Path
from typing import Any

import click
from lynceus_core.manifest.common import (
    PATH_FIELD,
    SOURCE_FILES_KEY,
    Manifest,
)

SourceEntry = dict[str, Any]

featurized_KEY = "featurized"
preprocessed_KEY = "preprocessed"
MODELS_KEY = "models"


def _scan_files(source_root: Path, source_glob: str) -> list[SourceEntry]:
    paths = sorted(path for path in source_root.glob(source_glob) if path.is_file())
    return Manifest.describe_files(paths, source_root)


def _require_files(
    source_root: Path, source_glob: str, label: str
) -> list[SourceEntry]:
    files = _scan_files(source_root, source_glob)
    if not files:
        raise click.ClickException(
            f"No {label} files matched {source_glob!r} under {source_root}"
        )
    return files


def _describe_model(model_file: Path | None, source_root: Path) -> list[SourceEntry]:
    if model_file is None:
        return []
    return Manifest.describe_files([model_file], source_root)


def _extract_names(files: list[SourceEntry]) -> list[str]:
    return [Path(entry[PATH_FIELD]).name for entry in files]


def _check_aligned(feature_names: list[str], conformer_names: list[str]) -> None:
    missing_preprocessed = sorted(set(feature_names) - set(conformer_names))
    missing_featurized = sorted(set(conformer_names) - set(feature_names))
    if missing_preprocessed or missing_featurized:
        raise click.ClickException(
            "Feature and conformer shards do not match: "
            f"missing preprocessed {missing_preprocessed}, "
            f"missing featurized {missing_featurized}"
        )


def _write_plan(plan: dict[str, list[str]], output_file: Path) -> None:
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(json.dumps(plan, separators=(",", ":")))


def _persist_source_files(files: list[SourceEntry], persist_file: Path) -> None:
    Manifest(data={SOURCE_FILES_KEY: files}, filepath=persist_file).save()


@click.command()
@click.option(
    "--source-root",
    required=True,
    type=click.Path(file_okay=False, path_type=Path),
    help="Directory the globs and model file are relative to in the plan.",
)
@click.option(
    "--featurized-glob",
    required=True,
    help="Glob, relative to --source-root, selecting the featurized files.",
)
@click.option(
    "--preprocessed-glob",
    required=True,
    help="Glob, relative to --source-root, selecting the conformer files.",
)
@click.option(
    "--model-file",
    default=None,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Surrogate model file to track, under --source-root.",
)
@click.option(
    "--output-file",
    default="/tmp/manifest.json",
    show_default=True,
    type=click.Path(dir_okay=False, path_type=Path),
    help="File the plan JSON is written to (read as an Argo output parameter).",
)
@click.option(
    "--persist-file",
    required=True,
    type=click.Path(dir_okay=False, path_type=Path),
    help="File the planned source files and their fingerprints are persisted to.",
)
def plan_surrogate_sample(
    source_root: Path,
    featurized_glob: str,
    preprocessed_glob: str,
    model_file: Path | None,
    output_file: Path,
    persist_file: Path,
) -> None:
    featurized = _require_files(source_root, featurized_glob, featurized_KEY)
    preprocessed = _require_files(source_root, preprocessed_glob, preprocessed_KEY)
    models = _describe_model(model_file, source_root)

    feature_names = _extract_names(featurized)
    conformer_names = _extract_names(preprocessed)
    _check_aligned(feature_names, conformer_names)

    _persist_source_files([*featurized, *preprocessed, *models], persist_file)
    _write_plan(
        {
            featurized_KEY: feature_names,
            preprocessed_KEY: conformer_names,
            MODELS_KEY: _extract_names(models),
        },
        output_file,
    )
    click.echo(
        f"Planned {len(featurized)} feature, {len(preprocessed)} conformer "
        f"and {len(models)} model files for sampling"
    )
