# models/local/docking_prep/src/docking_prep/models.py

"""Data models for receptor preparation."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class EnsemblePrepParams(BaseModel):
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
            "warnings on the EnsembleMemberPrepResult instead of raising."
        ),
    )


class EnsembleMemberPrepResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    member_id: str
    success: bool = Field(
        ..., description="True if preparation succeeded, False if an error occurred."
    )

    receptor_pdbqt_path: Path | None = Field(
        default=None,
        description="Path to the prepared rigid receptor PDBQT file. Set on success.",
    )
    params: EnsemblePrepParams | None = Field(
        default=None,
        description="The parameters actually used to produce this receptor. Set on success.",
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

    # Failure fields
    error_type: str | None = Field(
        default=None,
        description="Class name of the exception raised (e.g., 'ResidueTemplateError'). Populated on failure.",
    )
    error_message: str | None = Field(
        default=None,
        description="Detailed exception or failure message. Populated on failure.",
    )


class EnsemblePrepResults(BaseModel):
    model_config = ConfigDict(frozen=True)

    ensemble_id: str
    ensemble_content_hash: str
    results: list[EnsembleMemberPrepResult] = Field(
        default_factory=list,
        description="Combined list of member preparation outcomes (both successes and failures).",
    )

    @property
    def successes(self) -> list[EnsembleMemberPrepResult]:
        """Convenience helper to retrieve successful results."""
        return [r for r in self.results if r.success]

    @property
    def failures(self) -> list[EnsembleMemberPrepResult]:
        """Convenience helper to retrieve failed results."""
        return [r for r in self.results if not r.success]
