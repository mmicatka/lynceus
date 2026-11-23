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
    seed: int,
    num_random: int,
    num_top: int,
    model_path: str,
    exclude_inputs: list[str],
) -> None:
    import os
    import subprocess

    command = [
        "surrogate-sample",
        "--source-root",
        base_path,
        "--featurized-input",
        os.path.join(base_path, featurized_input_prefix, source),
        "--preprocessed-input",
        os.path.join(base_path, preprocessed_input_prefix, source),
        "--output",
        os.path.join(base_path, output_prefix, source),
        "--num-random",
        str(num_random),
        "--num-top",
        str(num_top),
        "--seed",
        str(seed),
    ]
    if model_path:
        command += ["--model", os.path.join(base_path, model_path)]
    for pattern in exclude_inputs:
        command += ["--exclude-input", os.path.join(base_path, pattern)]
    subprocess.run(command, check=True)
