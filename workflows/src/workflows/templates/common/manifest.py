# workflows/src/workflows/templates/common/manifest.py


def update_manifest_template(
    base_path: str,
    source: str,
    output: str,
    fields: dict,
):
    import json
    import os
    import subprocess

    subprocess.run(
        [
            "update-manifest",
            "--source",
            os.path.join(base_path, source),
            "--output",
            os.path.join(base_path, output),
            "--set",
            json.dumps(fields),
        ],
        check=True,
    )


def verify_manifest_template(
    base_path: str,
    manifest: str,
    expect: dict,
    source_globs: list[str],
    result_file: str,
):
    import json
    import os
    import subprocess

    cmd = [
        "verify-manifest",
        "--manifest",
        os.path.join(base_path, manifest),
        "--expect",
        json.dumps(expect),
        "--source-root",
        base_path,
        "--result-file",
        result_file,
    ]

    for source_glob in source_globs:
        cmd.extend(["--source-glob", source_glob])

    subprocess.run(cmd, check=True)
