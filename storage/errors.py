"""Storage-layer errors shared by provider implementations."""

from __future__ import annotations


class StorageConflictError(RuntimeError):
    """Raised when a conditional storage write loses a concurrency race."""
