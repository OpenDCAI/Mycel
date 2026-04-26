"""Messaging domain errors that HTTP/tool surfaces can map explicitly."""

from __future__ import annotations


class ChatNotCaughtUpError(RuntimeError):
    """Raised when a sender must read newer chat messages before replying."""
