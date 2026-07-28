# modules/local/docking_prep/src/docking_prep/__init__.py

from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("docking-prep")
except PackageNotFoundError:
    __version__ = "unknown"
