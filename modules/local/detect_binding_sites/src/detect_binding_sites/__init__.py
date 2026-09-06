# modules/local/detect_binding_sites/__init__.py

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("detect-binding-sites")
except PackageNotFoundError:
    __version__ = "unknown"
