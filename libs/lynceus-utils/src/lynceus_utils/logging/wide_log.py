# libs/lynceus-utils/src/lynceus_utils/logging/wide_log.py

import functools
import inspect
import time

from structlog.stdlib import BoundLogger


def wide_log(logger: BoundLogger):
    """
    Decorator to wrap a function in a wide log event.
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.perf_counter()

            sig = inspect.signature(func)
            bound_args = sig.bind(*args, **kwargs)
            bound_args.apply_defaults()

            local_logger = logger.bind(**bound_args.arguments)

            try:
                result = func(*args, **kwargs)

                duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
                local_logger.info(
                    f"{func.__name__}.completed",
                    status="success",
                    duration_ms=duration_ms,
                )

                return result

            except Exception as e:
                duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
                local_logger.error(
                    f"{func.__name__}.failed",
                    status="failed",
                    duration_ms=duration_ms,
                    error_type=type(e).__name__,
                    error_message=str(e),
                )
                raise

        return wrapper

    return decorator
