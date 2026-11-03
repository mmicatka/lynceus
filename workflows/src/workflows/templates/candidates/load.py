# workflows/src/workflows/templates/candidates/load.py


def load_candidates_template(
    base_path: str,
    source: str,
    source_prefix: str,
    parquet_prefix: str,
    scratch_dir: str = "",
    files_per_stage: str = "",
    transfers: str = "",
):
    import os
    import subprocess

    optional_flags = {
        "--scratch-dir": scratch_dir,
        "--files-per-stage": files_per_stage,
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
