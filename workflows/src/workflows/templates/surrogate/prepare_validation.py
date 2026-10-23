# workflows/src/workflows/templates/surrogate/prepare_validation.py


def surrogate_prepare_validation_template(
    validation_path: str, active_percentile: float
):
    import subprocess

    cmd = [
        "surrogate-prepare-validation ",
        "--validation-path",
        validation_path,
        "--active-percentile",
        str(active_percentile),
    ]

    subprocess.run(cmd, check=True)
