# workflows/src/workflows/templates/candidates/shard.py


def shard_candidates_template(
    base_path: str,
    input_prefix: str,
    output_prefix: str,
    num_shards: int,
    scratch_path: str,
    max_batch_gib: int,
    transfers: int = 4,
    id_column: str = "id",
    num_workers: str = "auto",
):
    import os
    import subprocess

    subprocess.run(
        [
            "shard-candidates",
            "--input",
            os.path.join(base_path, input_prefix),
            "--output",
            os.path.join(base_path, output_prefix),
            "--scratch-dir",
            scratch_path,
            "--num-shards",
            str(num_shards),
            "--max-batch-gib",
            str(max_batch_gib),
            "--transfers",
            str(transfers),
            "--id-column",
            id_column,
            "--num-workers",
            str(num_workers),
        ],
        check=True,
    )
