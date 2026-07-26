# modules/local/docking_prep/src/docking_prep/ligand/models.py


from dataclasses import dataclass, field


@dataclass(frozen=True)
class ConformerRecord:
    conformer_id: str
    pdbqt_text: str
    mmff_energy: float
    rank: int  # 0 = lowest energy among retained conformers


@dataclass(frozen=True)
class CandidateResult:
    candidate_id: str
    source_smiles: str
    protonated_smiles: str | None
    conformers: list[ConformerRecord] = field(default_factory=list)
    n_confs_requested: int = 0
    n_confs_embedded: int = 0
    random_seed: int = 0
    ph_min: float = 0.0
    ph_max: float = 0.0
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


@dataclass(frozen=True)
class EmbeddedConformer:
    conf_id: int  # RDKit's internal conformer id on the working Mol
    mmff_energy: float
