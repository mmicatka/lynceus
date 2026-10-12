# workflows/src/workflows/templates/targets/generate_manifest.py


def generate_manifest_template(
    base_path: str,
    input_path: str,
    output_path: str,
    ensemble_id: str,
    structure_glob: str,
):
    import os
    import subprocess

    subprocess.run(
        [
            "generate-manifest",
            "--input",
            os.path.join(base_path, input_path),
            "--output",
            os.path.join(base_path, output_path),
            "--id",
            ensemble_id,
            "--structure-glob",
            structure_glob,
        ],
        check=True,
    )
