# libs/lynceus-core/src/lynceus_core/manifest/fingerprint.py


import os
from pathlib import Path
from typing import Dict, Union

from lynceus_core.io.retry import DEFAULT_RETRY_POLICY, RetryPolicy, retry_call

FINGERPRINT_KEY = "fingerprint"
SIZE_FIELD = "size"
FINGERPRINT_FIELDS = SIZE_FIELD


def _stat_once(path: Union[str, Path]) -> Dict[str, int]:
    stat = os.stat(path)
    return {SIZE_FIELD: stat.st_size}


def fingerprint_file(
    path: Union[str, Path],
    policy: RetryPolicy = DEFAULT_RETRY_POLICY,
) -> Dict[str, int]:
    return retry_call(lambda: _stat_once(path), f"stat {path}", policy)
