# workflows/src/workflows/templates/candidates/load.py


def load_candidates_template(
    source: str, mount_path: str, source_prefix: str, parquet_prefix: str
):
    import os
    import subprocess

    subprocess.run(
        [
            "load-candidates",
            "--input",
            os.path.join(mount_path, source_prefix, source),
            "--output",
            os.path.join(mount_path, parquet_prefix),
        ],
        check=True,
    )
