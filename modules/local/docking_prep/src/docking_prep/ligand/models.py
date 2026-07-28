# modules/local/docking_prep/src/docking_prep/ligand/models.py


from dataclasses import dataclass, field

import msgpack

from docking_prep.utils import content_hash


@dataclass(frozen=True)
class ConformerRecord:
    conformer_id: str
    pdbqt_text: str
    mmff_energy: float
    rank: int  # 0 = lowest energy among retained conformers


@dataclass(frozen=True)
class Conformers:
    id: str
    source_smiles: str
    protonated_smiles: str | None
    conformers: list[ConformerRecord] = field(default_factory=list)
    source_tool: str | None = None
    n_confs_requested: int = 0
    n_confs_embedded: int = 0
    random_seed: int = 0
    ph_min: float = 0.0
    ph_max: float = 0.0
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None

    def to_record_bytes(self) -> bytes:
        """Pack this candidate's kept conformers into a single msgpack blob.

        Includes only what's needed to reconstruct a docking-ready set:
        protonation state, per-conformer PDBQT text + rank/energy, and a
        content hash. This intentionally excludes generation-parameter
        metadata (n_confs_requested, ph range, etc.) that lived in the old
        per-candidate manifest.yaml — flagging in case something downstream
        still expects it.
        """
        conformer_bytes = b"".join(
            c.pdbqt_text.encode("utf-8") for c in self.conformers
        )
        payload = {
            "id": self.id,
            "source_smiles": self.source_smiles,
            "protonated_smiles": self.protonated_smiles,
            "n_confs_embedded": self.n_confs_embedded,
            "content_hash": content_hash(conformer_bytes),
            "conformers": [
                {
                    "id": c.conformer_id,
                    "pdbqt": c.pdbqt_text,
                    "mmff_energy": round(c.mmff_energy, 4),
                    "rank": c.rank,
                }
                for c in self.conformers
            ],
        }
        return msgpack.packb(payload, use_bin_type=True)
