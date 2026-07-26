# libs/lynceus-chem/src/lynceus_chem/__init__.py

from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("lynceus-chem")
except PackageNotFoundError:
    __version__ = "unknown"
