# modules/local/feature_generation/src/feature_generation/features/__init__.py

from typing import Callable, Type

from .atom_pair import AtomPairFeature
from .autocorr import AutocorrFeature
from .cns_mpo import CNSMPOFeature
from .descriptors import DescriptorsFeature
from .e3fp import E3FPFeature
from .ecfp import ECFPFeature
from .electroshape import ElectroShapeFeature
from .feature_generator import FeatureGenerator
from .functional_groups import FunctionalGroupsFeature
from .morse import MORSEFeature
from .pharmacophore_3d import Pharmacophore3dFeature
from .rdf import RDFFeature
from .topological_torsion import TopologicalTorsionFeature
from .usrcat import USRCATFeature
from .whim import WHIMFeature

__all__ = [
    # features
    "AtomPairFeature",
    "AutocorrFeature",
    "CNSMPOFeature",
    "DescriptorsFeature",
    "E3FPFeature",
    "ECFPFeature",
    "ElectroShapeFeature",
    "FunctionalGroupsFeature",
    "MORSEFeature",
    "Pharmacophore3dFeature",
    "RDFFeature",
    "TopologicalTorsionFeature",
    "USRCATFeature",
    "WHIMFeature",
    # utils
    "FeatureGenerator",
    "FEATURE_GENERATOR_REGISTRY",
]

_FEATURE_CLASSES: list[Type[FeatureGenerator]] = [
    AtomPairFeature,
    AutocorrFeature,
    CNSMPOFeature,
    DescriptorsFeature,
    E3FPFeature,
    ECFPFeature,
    ElectroShapeFeature,
    FunctionalGroupsFeature,
    MORSEFeature,
    Pharmacophore3dFeature,
    RDFFeature,
    TopologicalTorsionFeature,
    USRCATFeature,
    WHIMFeature,
]

FEATURE_GENERATOR_REGISTRY: dict[str, Callable[[], FeatureGenerator]] = {
    cls.name: cls for cls in _FEATURE_CLASSES
}
