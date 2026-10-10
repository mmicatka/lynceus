# workflows/src/workflows/utils/volumes.py

from hera.workflows import RetryStrategy
from hera.workflows import models as m

IO_RETRY_STRATEGY = RetryStrategy(
    limit=5,
    backoff=m.Backoff(duration="30s", factor=m.IntOrString(root=2), max_duration="10m"),
)
