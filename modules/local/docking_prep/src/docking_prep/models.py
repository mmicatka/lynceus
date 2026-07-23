# models/local/docking_prep/src/docking_prep/models.py

"""Data models for receptor preparation."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class ReceptorPrepParams(BaseModel):
    model_config = ConfigDict(frozen=True)

    strip_waters: bool = Field(
        default=True, description="Remove HOH/WAT residues before PDBQT conversion."
    )
    strip_heteroatoms: bool = Field(
        default=True,
        description=(
            "Remove non-water HETATM residues (ligands, ions, cofactors) "
            "before PDBQT conversion. Does not affect standard amino acid "
            "residues even if present as HETATM records."
        ),
    )
    default_altloc: str = Field(
        default="A",
        description="Alternate location identifier to keep when a residue has multiple altlocs.",
    )
    allow_bad_residues: bool = Field(
        default=False,
        description=(
            "If False (default), any residue that fails Meeko's template "
            "matching raises ResidueTemplateError and no receptor is "
            "produced. If True, such residues are dropped and recorded as "
            "warnings on the ReceptorPrepResult instead of raising."
        ),
    )


class ReceptorPrepResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    member_id: str

    receptor_pdbqt_path: Path = Field(
        ..., description="Path to the prepared rigid receptor PDBQT file."
    )

    params: ReceptorPrepParams = Field(
        ..., description="The parameters actually used to produce this receptor."
    )

    dropped_residues: list[str] = Field(
        default_factory=list,
        description=(
            "Residue keys (e.g. 'A:4') dropped due to failed template "
            "matching. Only ever non-empty when params.allow_bad_residues "
            "was True — otherwise a template failure raises instead of "
            "populating this list."
        ),
    )


class ReceptorPrepFailure(BaseModel):
    model_config = ConfigDict(frozen=True)

    ensemble_id: str
    member_id: str
    error_type: str = Field(
        ...,
        description="Class name of the exception raised, e.g. 'ResidueTemplateError'.",
    )
    message: str


class ReceptorPrepResults(BaseModel):
    model_config = ConfigDict(frozen=True)

    ensemble_id: str
    ensemble_content_hash: str
    successes: list[ReceptorPrepResult]
    failures: list[ReceptorPrepFailure]
