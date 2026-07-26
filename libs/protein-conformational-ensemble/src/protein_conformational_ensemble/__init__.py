# libs/protein-conformational-ensemble/src/protein_conformational_ensemble/__init__.py

from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("protein-conformational-ensemble")
except PackageNotFoundError:
    __version__ = "unknown"
