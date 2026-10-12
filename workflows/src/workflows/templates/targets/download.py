# workflows/src/workflows/templates/targets/download.py


def download_pdbs_template(base_path: str, pdb_ids: str, output_prefix: str):
    import os
    import subprocess

    subprocess.run(
        [
            "download-pdbs",
            "--pdb-ids",
            pdb_ids,
            "--outdir",
            os.path.join(base_path, output_prefix),
        ],
        check=True,
    )
