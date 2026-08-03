# modules/local/surrogate_model/src/surrogate_model/cli.py

import logging

import click
import pandas as pd


def _configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


@click.group()
@click.option("--verbose", is_flag=True, help="Enable debug logging.")
def surrogate_model_train(verbose: bool) -> None:
    _configure_logging(verbose)


@surrogate_model_train.command()
@click.option(
    "--input",
    "input_path",
    required=True,
    type=click.Path(exists=True),
    help="Input file (CSV or parquet) containing a SMILES column.",
)
@click.option(
    "--output",
    "output_path",
    required=True,
    type=click.Path(),
    help="Output parquet path.",
)
@click.option("--smiles-column", default="smiles", show_default=True)
@click.option(
    "--id-column", default=None, help="Optional column to carry through as a row ID."
)
@click.option(
    "--passthrough-column",
    "passthrough_columns",
    multiple=True,
    help="Extra input column to carry through unchanged (e.g. a training target). Repeatable.",
)
@click.option(
    "--ecfp6", is_flag=True, help="Also compute ECFP6 (radius=3) fingerprint."
)
@click.option("--maccs", is_flag=True, help="Also compute MACCS keys.")
@click.option("--avalon", is_flag=True, help="Also compute Avalon fingerprint.")
@click.option(
    "--fail-on-unparseable",
    is_flag=True,
    help="Raise instead of dropping rows with unparseable SMILES.",
)
def featurize(
    input_path: str,
    output_path: str,
    smiles_column: str,
    id_column: str | None,
    passthrough_columns: tuple[str, ...],
    ecfp6: bool,
    maccs: bool,
    avalon: bool,
    fail_on_unparseable: bool,
) -> None:
    """Compute molecular features for every row of INPUT and write them to OUTPUT."""
    df = _read_table(input_path)

    config = FeaturizationConfig(
        smiles_column=smiles_column,
        id_column=id_column,
        passthrough_columns=passthrough_columns,
        fingerprints=FingerprintConfig(
            include_ecfp6=ecfp6, include_maccs=maccs, include_avalon=avalon
        ),
        drop_unparseable=not fail_on_unparseable,
    )

    click.echo(f"Featurizing {len(df)} row(s) from {input_path} ...")
    featurized = featurize_dataframe(df, config)
    featurized.to_parquet(output_path, index=False)
    click.echo(
        f"Wrote {len(featurized)} row(s), {len(featurized.columns)} column(s) to "
        f"{output_path}"
    )


@surrogate_model_train.command(name="train")
@click.option(
    "--input",
    "input_path",
    required=True,
    type=click.Path(exists=True),
    help="Featurized parquet file.",
)
@click.option(
    "--output",
    "output_path",
    required=True,
    type=click.Path(),
    help="Directory to save the model bundle to.",
)
@click.option(
    "--target-column",
    required=True,
    help="Column holding the docking score to predict (e.g. Vina/AD4 output), in kcal/mol.",
)
@click.option(
    "--score-source",
    required=True,
    type=click.Choice(KNOWN_SCORE_SOURCES, case_sensitive=False),
    help="Which docking engine produced the training scores. Stamped into the saved bundle "
    "so predictions are never silently mixed with a different engine's scale.",
)
@click.option(
    "--id-column",
    default=None,
    help="Row-ID column, excluded from features if present.",
)
@click.option(
    "--estimator",
    "estimator_name",
    default="random_forest",
    show_default=True,
    help="Estimator name (see `lynceus-surrogate list-estimators`).",
)
@click.option("--test-size", default=0.2, show_default=True, type=float)
@click.option("--cv-folds", default=5, show_default=True, type=int)
@click.option("--random-state", default=42, show_default=True, type=int)
@click.option(
    "--estimator-param",
    "estimator_params_raw",
    multiple=True,
    help="Extra estimator kwarg as key=value (repeatable), e.g. --estimator-param n_estimators=500",
)
def train_cmd(
    input_path: str,
    output_path: str,
    target_column: str,
    score_source: str,
    id_column: str | None,
    estimator_name: str,
    test_size: float,
    cv_folds: int,
    random_state: int,
    estimator_params_raw: tuple[str, ...],
) -> None:
    """Train a docking-score surrogate model on a featurized parquet file
    and save the bundle.

    The target column is expected to hold a docking engine's own score (a
    predicted binding free energy in kcal/mol, e.g. from Vina or AD4) — not a
    measured/experimental binding affinity.
    """
    df = pd.read_parquet(input_path)

    estimator_params = _parse_kv_params(estimator_params_raw)

    config = TrainConfig(
        target_column=target_column,
        score_source=score_source.lower(),
        id_column=id_column,
        estimator_name=estimator_name,
        estimator_params=estimator_params,
        test_size=test_size,
        cv_folds=cv_folds,
        random_state=random_state,
    )

    click.echo(
        f"Training regression model ({estimator_name}) on {len(df)} row(s), "
        f"target={target_column!r}, score_source={score_source!r} ..."
    )
    result = run_train(df, config)

    click.echo("Held-out metrics:")
    click.echo(json.dumps(result.metrics, indent=2))
    click.echo(f"CV scores ({cv_folds}-fold): {result.cv_scores}")

    bundle_dir = result.bundle.save(output_path)
    click.echo(f"Saved model bundle to {bundle_dir}")


@surrogate_model_train.command(name="predict")
@click.option(
    "--input",
    "input_path",
    required=True,
    type=click.Path(exists=True),
    help="Directory of featurized parquet files, or a glob pattern, to score.",
)
@click.option(
    "--model",
    "model_path",
    required=True,
    type=click.Path(exists=True),
    help="Path to a saved model bundle directory.",
)
@click.option(
    "--output",
    "output_path",
    required=True,
    type=click.Path(),
    help="Output parquet path for predictions.",
)
@click.option(
    "--id-column",
    default=None,
    help="Row-ID column to carry through into the output, if present.",
)
@click.option(
    "--batch-size",
    default=DEFAULT_BATCH_SIZE,
    show_default=True,
    type=int,
    help="Rows per streamed batch. Controls peak memory, not output layout.",
)
@click.option(
    "--prediction-column",
    default="predicted_docking_score",
    show_default=True,
    help="Output column name for the predicted docking score.",
)
def predict_cmd(
    input_path: str,
    model_path: str,
    output_path: str,
    id_column: str | None,
    batch_size: int,
    prediction_column: str,
) -> None:
    """Score a directory of featurized parquet files with a saved model, streaming via DuckDB.

    Predicts a docking engine's own score (binding free energy estimate, kcal/mol)
    — not a measured binding affinity. The output parquet's schema metadata
    records which docking engine (score_source) the loaded model was trained on.

    INPUT may be a directory (all *.parquet files in it, non-recursive) or an
    explicit glob. Files are streamed in fixed-size batches so arbitrarily large
    candidate libraries can be scored without loading them all into memory.
    """
    bundle = ModelBundle.load(model_path)
    config = PredictConfig(
        id_column=id_column,
        batch_size=batch_size,
        prediction_column=prediction_column,
    )

    click.echo(f"Scoring {input_path} with model bundle at {model_path} ...")
    summary = predict_directory(input_path, output_path, bundle, config)

    click.echo(
        f"Scored {summary.n_rows} row(s) across {len(summary.input_files)} file(s) "
        f"in {summary.n_batches} batch(es) using a {summary.score_source}-trained model; "
        f"wrote {output_path}"
    )


@surrogate_model_train.command(name="list-estimators")
def list_estimators() -> None:
    """List available regression estimators."""
    for name in ESTIMATORS:
        click.echo(name)


def _read_table(path: str) -> pd.DataFrame:
    if path.endswith(".parquet"):
        return pd.read_parquet(path)
    if path.endswith(".csv"):
        return pd.read_csv(path)
    raise click.ClickException(
        f"Unsupported input file extension for {path!r} (use .csv or .parquet)"
    )


def _parse_kv_params(raw: tuple[str, ...]) -> dict:
    params: dict = {}
    for item in raw:
        if "=" not in item:
            raise click.ClickException(
                f"Invalid --estimator-param {item!r}, expected key=value"
            )
        key, _, value = item.partition("=")
        params[key] = _coerce_scalar(value)
    return params


def _coerce_scalar(value: str):
    for caster in (int, float):
        try:
            return caster(value)
        except ValueError:
            continue
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    return value
