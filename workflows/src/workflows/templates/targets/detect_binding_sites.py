# workflows/src/workflows/templates/targets/detect_binding_sites.py


def detect_binding_sites_template(
    ensemble_path: str,
    output_path: str,
    num_workers: str = "auto",
):
    import subprocess

    subprocess.run(
        [
            "detect-binding-sites",
            "--ensemble",
            str(ensemble_path),
            "--out",
            str(output_path),
            "--num-workers",
            str(num_workers),
        ],
        check=True,
    )
