# workflows/src/workflows/templates/surrogate/sample.py


from workflows.registry.common.manifest_gate import MANIFEST_PATH


def plan_surrogate_sample_template(
    base_path: str,
    featurized_prefix: str,
    preprocessed_prefix: str,
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
        "--featurized-glob",
        os.path.join(featurized_prefix, source_glob),
        "--preprocessed-glob",
        os.path.join(preprocessed_prefix, source_glob),
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
    featurized_input_prefix: str,
    preprocessed_input_prefix: str,
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
            "--featurized-input",
            os.path.join(base_path, featurized_input_prefix, source),
            "--preprocessed-input",
            os.path.join(base_path, preprocessed_input_prefix, source),
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
    featurized_input_prefix: str,
    preprocessed_input_prefix: str,
    output_prefix: str,
    model_path: str,
    num_top: int,
    num_random: int,
    exclude_inputs: list[str] | None = None,
    id_column: str = "id",
    batch_size: int = 50000,
    seed: int | None = None,
    featurized: list[str] | None = None,
):
    import os
    import subprocess

    cmd = [
        "surrogate-sample-by-prediction",
        "--source-root",
        base_path,
        "--featurized-input",
        os.path.join(base_path, featurized_input_prefix, source),
        "--preprocessed-input",
        os.path.join(base_path, preprocessed_input_prefix, source),
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

    if exclude_inputs:
        for path in exclude_inputs:
            cmd.extend(["--exclude-input", path])

    if seed is not None:
        cmd.extend(["--seed", str(seed)])

    if featurized:
        for f in featurized:
            cmd.extend(["-f", f])

    subprocess.run(cmd, check=True)
