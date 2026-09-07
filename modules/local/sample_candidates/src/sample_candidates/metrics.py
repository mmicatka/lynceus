# modules/local/sample_candidates/src/sample_candidates/metrics.py

from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class StageTiming:
    elapsed_seconds: float = 0.0


@contextmanager
def timed_stage(stage_name: str, **context: object) -> Iterator[StageTiming]:
    context_str = " ".join(f"{k}={v}" for k, v in context.items())
    logger.info("METRIC stage=%s event=start %s", stage_name, context_str)
    start = time.perf_counter()
    timing = StageTiming()
    try:
        yield timing
    finally:
        timing.elapsed_seconds = time.perf_counter() - start
        logger.info(
            "METRIC stage=%s event=end elapsed_seconds=%.3f %s",
            stage_name,
            timing.elapsed_seconds,
            context_str,
        )
