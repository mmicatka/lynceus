# libs/protein-conformational-ensemble/src/pce/models.py

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

WeightSchemeType = Literal[
    "equilibrium_probability",
    "cluster_fraction",
    "experimental_occupancy",
    "uniform",
    "custom",
]

TrajectoryFormat = Literal["xtc", "dcd", "trr", "nc"]

CAPABILITY_STANDALONE_CIF = "standalone_cif"
CAPABILITY_TRAJECTORY_BACKED = "trajectory_backed"

KNOWN_CAPABILITIES = frozenset(
    {CAPABILITY_STANDALONE_CIF, CAPABILITY_TRAJECTORY_BACKED}
)


def _omit_none(**fields: Any) -> dict[str, Any]:
    return {k: v for k, v in fields.items() if v is not None}


@dataclass(frozen=True, slots=True)
class StandaloneStructure:
    uri: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StandaloneStructure:
        return cls(uri=data["uri"])

    def to_canonical(self) -> dict[str, Any]:
        return {"uri": self.uri}


@dataclass(frozen=True, slots=True)
class MultiModelStructure:
    uri: str
    model_index: int

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MultiModelStructure:
        return cls(uri=data["uri"], model_index=data["model_index"])

    def to_canonical(self) -> dict[str, Any]:
        return {"uri": self.uri, "model_index": self.model_index}


@dataclass(frozen=True, slots=True)
class TrajectoryStructure:
    topology_uri: str
    trajectory_uri: str
    frame_index: int
    trajectory_format: TrajectoryFormat

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TrajectoryStructure:
        return cls(
            topology_uri=data["topology_uri"],
            trajectory_uri=data["trajectory_uri"],
            frame_index=data["frame_index"],
            trajectory_format=data["trajectory_format"],
        )

    def to_canonical(self) -> dict[str, Any]:
        return {
            "topology_uri": self.topology_uri,
            "trajectory_uri": self.trajectory_uri,
            "frame_index": self.frame_index,
            "trajectory_format": self.trajectory_format,
        }


Structure = StandaloneStructure | MultiModelStructure | TrajectoryStructure


def structure_from_dict(data: dict[str, Any]) -> Structure:
    if "topology_uri" in data or "trajectory_uri" in data:
        return TrajectoryStructure.from_dict(data)
    if "model_index" in data:
        return MultiModelStructure.from_dict(data)
    return StandaloneStructure.from_dict(data)


@dataclass(frozen=True, slots=True)
class Weight:
    value: float
    type: WeightSchemeType | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Weight:
        return cls(value=data["value"], type=data.get("type"))

    def to_canonical(self) -> dict[str, Any]:
        return _omit_none(value=self.value, type=self.type)


@dataclass(frozen=True, slots=True)
class ResidueMapping:
    uri: str
    format: str = "pairwise_residue_table"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ResidueMapping:
        return cls(uri=data["uri"], format=data.get("format", "pairwise_residue_table"))

    def to_canonical(self) -> dict[str, Any]:
        return {"uri": self.uri, "format": self.format}


@dataclass(frozen=True, slots=True)
class ConformationalState:
    id: str
    structure: Structure
    weight: Weight | None = None
    residue_mapping: ResidueMapping | None = None
    provenance: dict[str, Any] | None = None
    thermodynamics: dict[str, Any] | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ConformationalState:
        return cls(
            id=data["id"],
            structure=structure_from_dict(data["structure"]),
            weight=Weight.from_dict(data["weight"]) if "weight" in data else None,
            residue_mapping=(
                ResidueMapping.from_dict(data["residue_mapping"])
                if "residue_mapping" in data
                else None
            ),
            provenance=data.get("provenance"),
            thermodynamics=data.get("thermodynamics"),
        )

    def to_canonical(self) -> dict[str, Any]:
        return _omit_none(
            id=self.id,
            structure=self.structure.to_canonical(),
            weight=self.weight.to_canonical() if self.weight is not None else None,
            residue_mapping=(
                self.residue_mapping.to_canonical()
                if self.residue_mapping is not None
                else None
            ),
            provenance=self.provenance,
            thermodynamics=self.thermodynamics,
        )


@dataclass(frozen=True, slots=True)
class WeightScheme:
    type: WeightSchemeType
    normalized: bool = False
    custom_semantics: dict[str, Any] | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WeightScheme:
        return cls(
            type=data["type"],
            normalized=data.get("normalized", False),
            custom_semantics=data.get("custom_semantics"),
        )

    def to_canonical(self) -> dict[str, Any]:
        return _omit_none(
            type=self.type,
            normalized=self.normalized,
            custom_semantics=self.custom_semantics,
        )


@dataclass(frozen=True, slots=True)
class ExternalTopologyReference:
    uri: str
    source: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExternalTopologyReference:
        return cls(uri=data["uri"], source=data.get("source"))

    def to_canonical(self) -> dict[str, Any]:
        return _omit_none(uri=self.uri, source=self.source)


@dataclass(frozen=True, slots=True)
class TopologyReference:
    conformational_state_id: str | None = None
    external_reference: ExternalTopologyReference | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TopologyReference:
        return cls(
            conformational_state_id=data.get("conformational_state_id"),
            external_reference=(
                ExternalTopologyReference.from_dict(data["external_reference"])
                if "external_reference" in data
                else None
            ),
        )

    def to_canonical(self) -> dict[str, Any]:
        return _omit_none(
            conformational_state_id=self.conformational_state_id,
            external_reference=(
                self.external_reference.to_canonical()
                if self.external_reference is not None
                else None
            ),
        )


@dataclass(frozen=True, slots=True)
class ParentEnsemble:
    id: str
    content_hash: str
    relationship: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ParentEnsemble:
        return cls(
            id=data["id"],
            content_hash=data["content_hash"],
            relationship=data["relationship"],
        )

    def to_canonical(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "content_hash": self.content_hash,
            "relationship": self.relationship,
        }


@dataclass(frozen=True, slots=True)
class Manifest:
    schema_version: str
    id: str
    content_hash: str
    parent_ensemble: ParentEnsemble | None
    topology_reference: TopologyReference
    conformational_states: tuple[ConformationalState, ...]
    weight_scheme: WeightScheme | None = None
    capabilities_required: tuple[str, ...] = field(default=(CAPABILITY_STANDALONE_CIF,))
    metadata: dict[str, Any] | None = None
    dynamics: dict[str, Any] | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Manifest:
        parent = data.get("parent_ensemble")
        return cls(
            schema_version=data["schema_version"],
            id=data["id"],
            content_hash=data["content_hash"],
            parent_ensemble=ParentEnsemble.from_dict(parent)
            if parent is not None
            else None,
            topology_reference=TopologyReference.from_dict(data["topology_reference"]),
            conformational_states=tuple(
                ConformationalState.from_dict(c) for c in data["conformational_states"]
            ),
            weight_scheme=(
                WeightScheme.from_dict(data["weight_scheme"])
                if "weight_scheme" in data
                else None
            ),
            capabilities_required=tuple(
                data.get("capabilities_required", [CAPABILITY_STANDALONE_CIF])
            ),
            metadata=data.get("metadata"),
            dynamics=data.get("dynamics"),
        )

    def to_canonical(self) -> dict[str, Any]:
        canonical = _omit_none(
            schema_version=self.schema_version,
            id=self.id,
            content_hash=self.content_hash,
            topology_reference=self.topology_reference.to_canonical(),
            weight_scheme=(
                self.weight_scheme.to_canonical()
                if self.weight_scheme is not None
                else None
            ),
            capabilities_required=list(self.capabilities_required),
            conformational_states=[
                c.to_canonical() for c in self.conformational_states
            ],
            metadata=self.metadata,
            dynamics=self.dynamics,
        )
        canonical["parent_ensemble"] = (
            self.parent_ensemble.to_canonical()
            if self.parent_ensemble is not None
            else None
        )
        return canonical

    def conformational_state_by_id(
        self, conformational_state_id: str
    ) -> ConformationalState | None:
        return next(
            (m for m in self.conformational_states if m.id == conformational_state_id),
            None,
        )
