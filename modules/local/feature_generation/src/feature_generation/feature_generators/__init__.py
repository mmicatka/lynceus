# modules/local/feature_generation/src/feature_generation/features/__init__.py

from typing import Callable

from .cns_mpo import CNSMPOFeature
from .descriptors import DescriptorsFeature
from .e3fp import E3FPFeature
from .ecfp import ECFPFeature
from .feature_generator import FeatureGenerator
from .pharmacophore_3d import Pharmacophore3dFeature
from .usrcat import USRCATFeature

__all__ = [
    # features
    "CNSMPOFeature",
    "DescriptorsFeature",
    "ECFPFeature",
    "E3FPFeature",
    "Pharmacophore3dFeature",
    "USRCATFeature",
    # utils
    "FeatureGenerator",
    "FEATURE_GENERATOR_REGISTRY",
]

FEATURE_GENERATOR_REGISTRY: dict[str, Callable[[], FeatureGenerator]] = {
    # CNSMPOFeature.name: CNSMPOFeature,
    DescriptorsFeature.name: DescriptorsFeature,
    ECFPFeature.name: ECFPFeature,
    E3FPFeature.name: E3FPFeature,
    Pharmacophore3dFeature.name: Pharmacophore3dFeature,
    USRCATFeature.name: USRCATFeature,
}
