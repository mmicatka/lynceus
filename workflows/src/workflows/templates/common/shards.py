# workflows/src/workflows/templates/common/shards.py


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
            "--source-root",
            base_path,
            "--input",
            os.path.join(base_path, input_path),
            "--output",
            os.path.join(base_path, output_path),
            "--memory-limit",
            "6GB",
        ],
        check=True,
    )


def verify_shard_layout_template(
    base_path: str,
    check: str,
    num_shards: str,
    filename_template: str,
    folder_prefix: str,
    shards_dir: str,
    staging_dir: str,
):
    import os
    import subprocess

    subprocess.run(
        [
            "verify-shard-layout",
            "--check",
            check,
            "--num-shards",
            str(num_shards),
            "--filename-template",
            filename_template,
            "--folder-prefix",
            folder_prefix,
            "--shards-dir",
            os.path.join(base_path, shards_dir),
            "--staging-dir",
            os.path.join(base_path, staging_dir),
        ],
        check=True,
    )
