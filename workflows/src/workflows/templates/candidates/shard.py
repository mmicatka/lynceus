# workflows/src/workflows/templates/candidates/shard.py


def shard_candidates_template(
    mount_path: str,
    input_prefix: str,
    output_prefix: str,
    num_shards: int,
    id_column: str = "id",
    num_workers: str = "auto",
):
    import os
    import subprocess

    subprocess.run(
        [
            "shard-candidates",
            "--input",
            os.path.join(mount_path, input_prefix),
            "--output",
            os.path.join(mount_path, output_prefix),
            "--num-shards",
            str(num_shards),
            "--id-column",
            id_column,
            "--num-workers",
            str(num_workers),
        ],
        check=True,
    )
