# modules/local/docking_run/src/docking_run/types/errors.py


class DockingError(RuntimeError):
    """Raised when a provider fails to dock (subprocess failure, bad output, etc.)."""
