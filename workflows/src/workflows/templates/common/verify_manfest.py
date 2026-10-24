# workflows/src/workflows/templates/common/verify_manifest.py


def verify_manifest_template(
    manifest_path: str,
    expect: dict | None = None,
):
    import json
    import subprocess

    subprocess.run(
        [
            "verify-manifest",
            "--manifest",
            manifest_path,
            "--expect",
            json.dumps(expect or {}),
            "--result-file",
            "/tmp/manifest_matches.txt",
        ],
        check=True,
    )
