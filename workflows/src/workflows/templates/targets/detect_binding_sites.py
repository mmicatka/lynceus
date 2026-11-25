# workflows/src/workflows/templates/targets/detect_binding_sites.py


def detect_binding_sites_template(
    ensemble_path: str,
    ensemble_id: str | None = None,
    output_dir: str | None = None,
    min_pocket_score: float = 10.0,
    num_workers: str = "auto",
):
    import subprocess

    cmd = [
        "detect-binding-sites",
        "--ensemble",
        str(ensemble_path),
        "--min-pocket-score",
        str(min_pocket_score),
        "--num-workers",
        str(num_workers),
    ]
    if ensemble_id is not None:
        cmd.extend(["--ensemble-id", str(ensemble_id)])
    if output_dir is not None:
        cmd.extend(["--output-dir", str(output_dir)])

    subprocess.run(cmd, check=True)
