# workflows/src/workflows/templates/candidates/generate_features.py


def generate_features_template(
    source: str,
    mount_path: str,
    input_prefix: str,
    output_prefix: str,
    features: list[str],
    num_workers: str = "auto",
):
    import os
    import subprocess

    cmd = [
        "generate-features",
        "--input",
        os.path.join(mount_path, input_prefix, source),
        "--output",
        os.path.join(mount_path, output_prefix, source),
        "--num-workers",
        str(num_workers),
    ]

    for feature in features:
        cmd.extend(["--features", feature])

    subprocess.run(cmd, check=True)
