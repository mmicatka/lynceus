# workflows/src/workflows/templates/candidates/preprocess.py


def plan_preprocess_candidates_template(
    base_path: str,
    input_prefix: str,
    persist_file: str,
    source_glob: str = "*",
    output_file: str = "/tmp/manifest.json",
):
    import os
    import subprocess

    subprocess.run(
        [
            "plan-preprocess-candidates",
            "--source-root",
            base_path,
            "--source-glob",
            os.path.join(input_prefix, source_glob),
            "--output-file",
            output_file,
            "--persist-file",
            os.path.join(base_path, persist_file),
        ],
        check=True,
    )


def generate_conformers_template(
    base_path: str,
    source: str,
    input_prefix: str,
    output_prefix: str,
    num_workers: str = "auto",
    batch_size: int = 10000,
    chunk_size: int = 25,
):
    import os
    import subprocess

    subprocess.run(
        [
            "generate-conformers",
            "--source-root",
            base_path,
            "--input",
            os.path.join(base_path, input_prefix, source),
            "--output",
            os.path.join(base_path, output_prefix, source),
            "--batch-size",
            str(batch_size),
            "--chunk-size",
            str(chunk_size),
            "--num-workers",
            str(num_workers),
        ],
        check=True,
    )


def generate_features_template(
    base_path: str,
    source: str,
    input_prefix: str,
    output_prefix: str,
    features: list[str],
    num_workers: str = "auto",
):
    import os
    import subprocess

    cmd = [
        "generate-features",
        "--source-root",
        base_path,
        "--input",
        os.path.join(base_path, input_prefix, source),
        "--output",
        os.path.join(base_path, output_prefix, source),
        "--num-workers",
        str(num_workers),
    ]

    for feature in features:
        cmd.extend(["--features", feature])

    subprocess.run(cmd, check=True)
