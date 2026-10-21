# workflows/src/workflows/templates/targets/detect_binding_sites.py


def detect_binding_sites_template(
    ensemble_path: str,
    min_pocket_score: float = 20.0,
    num_workers: str = "auto",
):
    import subprocess

    subprocess.run(
        [
            "detect-binding-sites",
            "--ensemble",
            str(ensemble_path),
            "--min-pocket-score",
            str(min_pocket_score),
            "--num-workers",
            str(num_workers),
        ],
        check=True,
    )
