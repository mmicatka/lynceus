# workflows/src/workflows/templates/targets/__init__.py

from .detect_binding_sites import detect_binding_sites_template
from .download import download_pdbs_template
from .generate_manifest import generate_manifest_template
from .resolve_binding_sites import resolve_binding_sites_template

__all__ = [
    "detect_binding_sites_template",
    "download_pdbs_template",
    "generate_manifest_template",
    "resolve_binding_sites_template",
]
