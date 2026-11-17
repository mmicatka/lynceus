# workflows/src/workflows/templates/candidates/preprocess.py


def preprocess_candidate_shard_template(
    base_path: str,
    source: str,
    input_prefix: str,
    output_prefix: str,
    manifest_prefix: str,
    num_workers: str = "auto",
    batch_size: int = 10000,
    chunk_size: int = 25,
):
    import os
    import subprocess

    subprocess.run(
        [
            "preprocess-candidate-shard",
            "--source-root",
            base_path,
            "--input",
            os.path.join(base_path, input_prefix, source),
            "--output",
            os.path.join(base_path, output_prefix, source),
            "--manifest-dir",
            os.path.join(base_path, manifest_prefix),
            "--batch-size",
            str(batch_size),
            "--chunk-size",
            str(chunk_size),
            "--num-workers",
            str(num_workers),
        ],
        check=True,
    )
