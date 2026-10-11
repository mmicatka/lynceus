# workflows/src/workflows/templates/candidates/sample.py


def sample_candidates_template(
    source: str,
    mount_path: str,
    source_prefix: str,
    parquet_prefix: str,
    num_samples: int,
):
    import os
    import subprocess

    subprocess.run(
        [
            "sample-candidates",
            "--input",
            os.path.join(mount_path, source_prefix, source),
            "--output",
            os.path.join(mount_path, parquet_prefix, source),
            "--num-samples",
            str(num_samples),
        ],
        check=True,
    )
