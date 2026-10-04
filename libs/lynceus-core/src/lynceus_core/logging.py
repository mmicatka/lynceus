# libs/lynceus-core/src/lynceus_core/logging.py


import functools
import inspect
import time
from collections.abc import Callable, Iterable
from typing import Any, TypeVar, cast

import structlog
from structlog.typing import FilteringBoundLogger

F = TypeVar("F", bound=Callable[..., Any])

_DEFAULT_EXCLUDE = ("self", "cls")


def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 2)


def _capture_arguments(
    signature: inspect.Signature,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    excluded: frozenset[str],
) -> dict[str, Any]:
    try:
        bound = signature.bind(*args, **kwargs)
    except TypeError:
        return {}
    bound.apply_defaults()
    return {
        name: value for name, value in bound.arguments.items() if name not in excluded
    }


def _log_success(
    logger: FilteringBoundLogger,
    name: str,
    started: float,
    arguments: dict[str, Any],
) -> None:
    logger.info(
        f"{name}.completed",
        status="success",
        duration_ms=_elapsed_ms(started),
        arguments=arguments,
    )


def _log_failure(
    logger: FilteringBoundLogger,
    name: str,
    started: float,
    arguments: dict[str, Any],
    error: Exception,
) -> None:
    logger.exception(
        f"{name}.failed",
        status="failed",
        duration_ms=_elapsed_ms(started),
        error_type=type(error).__name__,
        arguments=arguments,
    )


def wide_log(
    logger: FilteringBoundLogger | None = None,
    *,
    exclude: Iterable[str] = (),
) -> Callable[[F], F]:
    excluded = frozenset(exclude) | frozenset(_DEFAULT_EXCLUDE)

    def decorator(func: F) -> F:
        signature = inspect.signature(func)
        log = logger or structlog.get_logger(func.__module__)
        name = func.__qualname__

        if inspect.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                started = time.perf_counter()
                arguments = _capture_arguments(signature, args, kwargs, excluded)
                try:
                    result = await func(*args, **kwargs)
                except Exception as error:
                    _log_failure(log, name, started, arguments, error)
                    raise
                _log_success(log, name, started, arguments)
                return result

            return cast(F, async_wrapper)

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            started = time.perf_counter()
            arguments = _capture_arguments(signature, args, kwargs, excluded)
            try:
                result = func(*args, **kwargs)
            except Exception as error:
                _log_failure(log, name, started, arguments, error)
                raise
            _log_success(log, name, started, arguments)
            return result

        return cast(F, sync_wrapper)

    return decorator
