# workflows/src/workflows/templates/candidates/load.py


def plan_shard_candidates_template(
    source_root: str,
    source_glob: str,
    output_file: str,
    max_batch_gib: str,
):
    import subprocess

    args = [
        "plan-load-candidates",
        "--source-root",
        source_root,
        "--source-glob",
        source_glob,
        "--output-file",
        output_file,
        "--max-batch-gib",
        max_batch_gib,
    ]

    subprocess.run([str(arg) for arg in args], check=True)


def shard_candidates_template(
    base_path: str,
    batch: list[str],
    output_prefix: str,
    num_shards: str,
    scratch_dir: str = "",
    transfers: str = "",
    chunk_size: str = "",
):
    import os
    import subprocess

    optional_flags = {
        "--scratch-dir": scratch_dir,
        "--transfers": transfers,
        "--chunk-size": chunk_size,
    }
    extra_args = [
        arg
        for flag, value in optional_flags.items()
        if value != ""
        for arg in (flag, str(value))
    ]
    output = os.path.join(base_path, output_prefix)

    for path in batch:
        subprocess.run(
            [
                "shard-candidates",
                "--input",
                os.path.join(base_path, path),
                "--output",
                output,
                "--num-shards",
                str(num_shards),
                *extra_args,
            ],
            check=True,
        )
