# workflows/src/workflows/templates/surrogate/sample.py


from workflows.registry.common.manifest_gate import MANIFEST_PATH


def plan_surrogate_sample_template(
    base_path: str,
    features_prefix: str,
    conformers_prefix: str,
    persist_file: str,
    source_glob: str = "*.parquet",
    model_path: str = "",
    output_file: str = MANIFEST_PATH,
):
    import os
    import subprocess

    cmd = [
        "plan-surrogate-sample",
        "--source-root",
        base_path,
        "--features-glob",
        os.path.join(features_prefix, source_glob),
        "--conformers-glob",
        os.path.join(conformers_prefix, source_glob),
        "--output-file",
        output_file,
        "--persist-file",
        os.path.join(base_path, persist_file),
    ]

    if model_path:
        cmd.extend(["--model-file", model_path])

    subprocess.run(cmd, check=True)


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
            "--source-root",
            base_path,
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
        "--source-root",
        base_path,
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
