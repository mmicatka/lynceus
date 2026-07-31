# modules/local/docking_run/src/docking_run/vina.py


class VinaProvider(DockingProvider):
    def check_installed(self) -> bool:
        # Check if 'vina' is in the system PATH
        import shutil

        return shutil.which("vina") is not None

    def dock(self, receptor: Path, ligand: Path, output: Path, **kwargs) -> bool:
        print(f"Running AutoDock Vina on {ligand.name}...")
        # Example subprocess call
        # cmd = ["vina", "--receptor", str(receptor), "--ligand", str(ligand), "--out", str(output)]
        # subprocess.run(cmd, check=True)
        return True
