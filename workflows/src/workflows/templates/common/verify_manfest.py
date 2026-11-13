# workflows/src/workflows/templates/common/verify_manifest.py


def verify_manifest_template(
    base_path: str,
    manifest: str,
    expect: dict,
    source_glob: str,
    result_file: str,
):
    import json
    import os
    import subprocess

    subprocess.run(
        [
            "verify-manifest",
            "--manifest",
            os.path.join(base_path, manifest),
            "--expect",
            json.dumps(expect),
            "--source-root",
            base_path,
            "--source-glob",
            source_glob,
            "--result-file",
            result_file,
        ],
        check=True,
    )
