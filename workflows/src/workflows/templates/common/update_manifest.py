# workflows/src/workflows/templates/common/update_manifest.py


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
