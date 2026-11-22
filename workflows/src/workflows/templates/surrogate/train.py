# workflows/src/workflows/templates/surrogate/train.py


from typing import List, Optional


def surrogate_train_template(
    base_path: str,
    train_features: str,
    train_labels: str,
    validation_features: str,
    validation_labels: str,
    model_path: str,
    features: Optional[List[str]] = None,
    eval_percents: Optional[List[float]] = None,
):
    import subprocess

    cmd = [
        "surrogate-train",
        "--source-root",
        base_path,
        "--train-features",
        train_features,
        "--train-labels",
        train_labels,
        "--validation-features",
        validation_features,
        "--validation-labels",
        validation_labels,
        "--model-path",
        model_path,
    ]

    if features:
        for feature in features:
            cmd.extend(["--features", feature])

    if eval_percents:
        for pct in eval_percents:
            cmd.extend(["--eval-percents", str(pct)])

    subprocess.run(cmd, check=True)
