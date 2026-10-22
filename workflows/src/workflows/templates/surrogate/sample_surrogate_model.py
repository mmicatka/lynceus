# workflows/src/workflows/templates/surrogate/surrogate_sample.py


def surrogate_sample_template(
    base_path: str,
    source: str,
    features_input_prefix: str,
    conformers_input_prefix: str,
    output_prefix: str,
    num_samples: int,
    id_column: str = "id",
):
    import os
    import subprocess

    subprocess.run(
        [
            "surrogate-sample",
            "--features-input",
            os.path.join(base_path, features_input_prefix, source),
            "--conformers-input",
            os.path.join(base_path, conformers_input_prefix, source),
            "--output",
            os.path.join(base_path, output_prefix, source),
            "--num-samples",
            str(num_samples),
            "--id-column",
            id_column,
        ],
        check=True,
    )


def surrogate_sample_by_prediction_template(
    base_path: str,
    source: str,
    features_input_prefix: str,
    conformers_input_prefix: str,
    output_prefix: str,
    model_path: str,
    num_top: int,
    num_random: int,
    id_column: str = "id",
    batch_size: int = 50000,
    seed: int | None = None,
    features: list[str] | None = None,
):
    import os
    import subprocess

    cmd = [
        "surrogate-sample-by-prediction",
        "--features-input",
        os.path.join(base_path, features_input_prefix, source),
        "--conformers-input",
        os.path.join(base_path, conformers_input_prefix, source),
        "--model",
        model_path,
        "--output",
        os.path.join(base_path, output_prefix, source),
        "--num-top",
        str(num_top),
        "--num-random",
        str(num_random),
        "--id-column",
        id_column,
        "--batch-size",
        str(batch_size),
    ]

    if seed is not None:
        cmd.extend(["--seed", str(seed)])

    if features:
        for f in features:
            cmd.extend(["-f", f])

    subprocess.run(cmd, check=True)
