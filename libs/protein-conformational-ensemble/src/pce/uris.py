# libs/protein-conformational-ensemble/src/pce/uris.py

from __future__ import annotations

from pathlib import PurePosixPath


def split_scheme(uri: str) -> tuple[str, str]:
    if "://" in uri:
        scheme, _, rest = uri.partition("://")
        return scheme, rest
    return "file", uri


def join_uri(package_root: str, relative_uri: str) -> str:
    scheme, rest = split_scheme(package_root)
    joined = str(PurePosixPath(rest) / relative_uri)
    if scheme == "file":
        return joined
    return f"{scheme}://{joined}"
