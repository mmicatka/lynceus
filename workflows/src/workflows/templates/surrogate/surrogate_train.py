# workflows/src/workflows/templates/surrogate/surrogate_train.py


from typing import List, Optional


def surrogate_train_template(
    train_features: str,
    train_labels: str,
    validation_features: str,
    validation_labels: str,
    model_path: str,
    features: Optional[List[str]] = None,
):
    import subprocess

    cmd = [
        "surrogate-train",
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

    subprocess.run(cmd, check=True)
