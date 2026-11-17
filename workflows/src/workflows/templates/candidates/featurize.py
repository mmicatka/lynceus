# workflows/src/workflows/templates/candidates/featurize.py


def featurize_candidate_shard_template(
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
        "featurize-candidate-shard",
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
