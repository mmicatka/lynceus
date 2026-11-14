# workflows/src/workflows/templates/candidates/sample.py


def sample_candidates_template(
    base_path: str,
    source: str,
    source_prefix: str,
    parquet_prefix: str,
    num_samples: int,
):
    import os
    import subprocess

    source_root = os.path.join(base_path, source_prefix)

    subprocess.run(
        [
            "sample-candidates",
            "--input",
            os.path.join(source_root, source),
            "--source-root",
            source_root,
            "--output",
            os.path.join(base_path, parquet_prefix, source),
            "--num-samples",
            str(num_samples),
        ],
        check=True,
    )
