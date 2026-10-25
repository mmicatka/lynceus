# workflows/src/workflows/template/docking/run_docking.py


def run_docking_template(
    ensemble: str,
    member_id: str,
    ligands_path: str,
    center: tuple[float, float, float],
    site_id: str,
    output_path: str,
    size: tuple[float, float, float] | None = None,
    search_mode: str = "balance",
    num_modes: int = 1,
    batch_size: int | None = None,
    out_dir: str | None = None,
    parquet_batch_rows: int = 10000,
    default_altloc: str = "A",
    allow_bad_residues: bool = True,
):
    import subprocess

    cmd = [
        "run-docking",
        "--ensemble",
        str(ensemble),
        "--member-id",
        str(member_id),
        "--ligands-path",
        str(ligands_path),
        "--center",
        str(center[0]),
        str(center[1]),
        str(center[2]),
        "--site-id",
        str(site_id),
        "--output",
        str(output_path),
        "--search-mode",
        str(search_mode),
        "--num-modes",
        str(num_modes),
        "--parquet-batch-rows",
        str(parquet_batch_rows),
        "--default-altloc",
        str(default_altloc),
    ]

    if size is not None:
        cmd.extend(["--size", str(size[0]), str(size[1]), str(size[2])])

    if batch_size is not None:
        cmd.extend(["--batch-size", str(batch_size)])

    if out_dir is not None:
        cmd.extend(["--out-dir", str(out_dir)])

    if allow_bad_residues:
        cmd.append("--allow-bad-residues")

    subprocess.run(cmd, check=True)
