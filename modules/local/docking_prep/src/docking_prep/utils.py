# modules/local/docking_prep/src/docking_prep/utils.py

import blake3


def sanitize_dirname(candidate_id: str) -> str:
    safe = "".join(c if (c.isalnum() or c in "._-") else "_" for c in candidate_id)
    return safe or "unnamed_candidate"


def content_id(data: bytes, length: int = 16) -> str:
    return blake3.blake3(data).hexdigest(length // 2)


def content_hash(data: bytes) -> str:
    return f"blake3:{blake3.blake3(data).hexdigest()}"
