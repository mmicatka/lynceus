# workflows/src/workflows/templates/candidates/sample.py


def sample_candidates_template(
    source: str,
    mount_path: str,
    source_prefix: str,
    parquet_prefix: str,
    num_samples: int,
    rows_per_file: int = 50000,
):
    import os
    import subprocess

    subprocess.run(
        [
            "sample_reservoir",
            "--input",
            os.path.join(mount_path, source_prefix, source),
            "--output",
            os.path.join(mount_path, parquet_prefix),
            "--num-samples",
            str(num_samples),
            "--rows-per-file",
            str(rows_per_file),
        ],
        check=True,
    )
