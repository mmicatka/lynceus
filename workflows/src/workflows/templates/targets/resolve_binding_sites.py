# workflows/src/workflows/templates/targets/resolve_sites.py


def resolve_binding_sites_template(
    base_path: str,
    ensembles_prefix: str,
    ensemble_ids: list[str],
):
    import os
    import subprocess

    cmd = [
        "resolve-binding-sites",
        "--ensembles-root",
        os.path.join(base_path, ensembles_prefix),
    ]
    for ensemble_id in ensemble_ids:
        cmd.extend(["--ensemble-id", ensemble_id])

    subprocess.run(cmd, check=True)
