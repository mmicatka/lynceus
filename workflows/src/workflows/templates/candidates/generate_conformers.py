# workflows/src/workflows/templates/candidates/generate_conformers.py


def generate_conformers_template(
    source: str,
    mount_path: str,
    input_prefix: str,
    output_prefix: str,
    num_workers: str = "auto",
    batch_size: int = 10000,
    chunk_size: int = 25,
):
    import os
    import subprocess

    subprocess.run(
        [
            "generate-conformers",
            "--input",
            os.path.join(mount_path, input_prefix, source),
            "--output",
            os.path.join(mount_path, output_prefix, source),
            "--batch-size",
            str(batch_size),
            "--chunk-size",
            str(chunk_size),
            "--num-workers",
            str(num_workers),
        ],
        check=True,
    )
