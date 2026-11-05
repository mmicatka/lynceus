# workflows/src/workflows/templates/candidates/load.py


def load_candidates_template(
    base_path: str,
    source: str,
    source_prefix: str,
    parquet_prefix: str,
    scratch_dir: str = "",
    max_batch_gib: str = "",
    transfers: str = "",
):
    import os
    import subprocess

    optional_flags = {
        "--scratch-dir": scratch_dir,
        "--max-batch-gib": max_batch_gib,
        "--transfers": transfers,
    }
    extra_args = [
        arg for flag, value in optional_flags.items() if value for arg in (flag, value)
    ]

    subprocess.run(
        [
            "load-candidates",
            "--input",
            os.path.join(base_path, source_prefix, source),
            "--output",
            os.path.join(base_path, parquet_prefix),
            *extra_args,
        ],
        check=True,
    )
