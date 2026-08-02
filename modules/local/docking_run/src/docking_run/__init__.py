# modules/local/docking_run/src/docking_run/__init__.py

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("docking-prep")
except PackageNotFoundError:
    __version__ = "unknown"
