# workflows/src/workflows/templates/common/merge_shards.py


def merge_shards_template(
    mount_path: str,
    input_path: str,
    output_path: str,
    num_workers: str = "auto",
):
    import os
    import subprocess

    subprocess.run(
        [
            "merge-shards",
            "--input",
            os.path.join(mount_path, input_path),
            "--output",
            os.path.join(mount_path, output_path),
            "--num-workers",
            str(num_workers),
        ],
        check=True,
    )
