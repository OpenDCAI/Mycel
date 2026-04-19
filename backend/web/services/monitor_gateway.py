"""Compatibility shell for the Monitor gateway."""

from backend.monitor.infrastructure.web import gateway as _impl


def __getattr__(name: str):
    return getattr(_impl, name)


def __dir__():
    return sorted(set(globals()) | set(dir(_impl)))
