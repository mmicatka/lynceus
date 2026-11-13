# workflows/src/workflows/templates/common/verify_shard_layout.py


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
