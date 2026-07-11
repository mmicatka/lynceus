# libs/protein-conformational-ensemble/src/pce/errors.py

from __future__ import annotations


class PceError(Exception):
    """Base class for all errors raised by this library."""


class SchemaValidationError(PceError):
    """Raised when a manifest fails structural JSON Schema validation."""


class SemanticValidationError(PceError):
    """Raised when a manifest passes schema validation but violates a normative semantic rule.

    This error is used for validation rules that are explicitly out of scope
    for the structural JSON Schema.
    """


class UnsupportedSchemaVersionError(PceError):
    """Raised when a consumer encounters a ``schema_version`` value it does not support.

    A consumer MUST reject any unsupported schema versions.
    """


class UnsupportedCapabilityError(PceError):
    """Raised when a consumer encounters a declared ``capabilities_required`` entry it does not support.

    A consumer MUST reject the package rather than silently ignoring the unsupported capability.
    """


class ContentHashMismatchError(PceError):
    """Raised when a recomputed ``content_hash`` does not match the value declared in the manifest.

    This indicates silent corruption or data drift.
    """


class CanonicalizationError(PceError):
    """Raised when a value cannot be canonicalized.

    This occurs if data contains ``NaN`` or ``Infinity``, which producers MUST
    reject before attempting to hash the manifest.
    """
