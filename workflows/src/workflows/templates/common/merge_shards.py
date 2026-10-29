# workflows/src/workflows/templates/common/merge_shards.py


def merge_shards_template(
    base_path: str,
    input_path: str,
    output_path: str,
):
    import os
    import subprocess

    subprocess.run(
        [
            "merge-shards",
            "--input",
            os.path.join(base_path, input_path),
            "--output",
            os.path.join(base_path, output_path),
            "--memory-limit",
            "6GB",
        ],
        check=True,
    )
