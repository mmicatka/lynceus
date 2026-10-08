# workflows/src/workflows/templates/common/merge_shards.py


def merge_shards_template(
    mount_path: str,
    input_prefix: str,
    output_prefix: str,
    num_workers: str = "auto",
):
    import os
    import subprocess

    subprocess.run(
        [
            "merge-shards",
            "--input",
            os.path.join(mount_path, input_prefix),
            "--output",
            os.path.join(mount_path, output_prefix),
            "--num-workers",
            str(num_workers),
        ],
        check=True,
    )
