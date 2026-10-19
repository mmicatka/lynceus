# projects/lynceus-dock/src/lynceus_dock/common/logging.py


import sys
from typing import Any, Iterable, Iterator, TypeVar

import structlog

T = TypeVar("T")


def configure_logging() -> None:
    renderer = (
        structlog.dev.ConsoleRenderer(colors=True)
        if sys.stdout.isatty()
        else structlog.processors.JSONRenderer()
    )
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            renderer,
        ]
    )


def _progress_message(processed: int, total: int | None) -> str:
    if total is None:
        return f"Processed {processed}"
    return f"Processed {processed} out of {total}"


def log_progress(
    items: Iterable[T],
    *,
    total: int | None,
    every: int,
    logger: Any = None,
    **context: Any,
) -> Iterator[T]:
    log = logger or structlog.get_logger()
    processed = 0
    last_logged = 0
    for item in items:
        yield item
        processed += 1
        if processed % every == 0:
            last_logged = processed
            log.info(
                _progress_message(processed, total),
                processed=processed,
                total=total,
                **context,
            )
    if processed != last_logged:
        log.info(
            _progress_message(processed, total),
            processed=processed,
            total=total,
            **context,
        )
