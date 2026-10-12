# workflows/src/workflows/templates/candidates/load.py


def load_candidates_template(
    base_path: str, source: str, source_prefix: str, parquet_prefix: str
):
    import os
    import subprocess

    subprocess.run(
        [
            "load-candidates",
            "--input",
            os.path.join(base_path, source_prefix, source),
            "--output",
            os.path.join(base_path, parquet_prefix),
        ],
        check=True,
    )
