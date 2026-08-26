# modules/local/docking_run/src/docking_run/types/ligand_record.py


from dataclasses import dataclass


@dataclass(frozen=True)
class LigandRecord:
    ligand_id: str
    mol_bytes: bytes  # RDKit Mol serialized (e.g. Mol.ToBinary())
