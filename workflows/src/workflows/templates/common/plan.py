# workflows/src/workflows/templates/common/plan.py


def generate_plan_template(
    base_path: str,
    input_prefix: str,
    persist_file: str,
    source_glob: str = "*",
    output_file: str = "/tmp/manifest.json",
):
    import os
    import subprocess

    subprocess.run(
        [
            "generate-plan",
            "--source-root",
            base_path,
            "--source-glob",
            os.path.join(input_prefix, source_glob),
            "--output-file",
            output_file,
            "--persist-file",
            os.path.join(base_path, persist_file),
        ],
        check=True,
    )
