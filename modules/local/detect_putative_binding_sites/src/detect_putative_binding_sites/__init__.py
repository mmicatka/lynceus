# modules/local/detect_putative_sites/__init__.py

from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("detect-putative-binding-sites")
except PackageNotFoundError:
    __version__ = "unknown"
