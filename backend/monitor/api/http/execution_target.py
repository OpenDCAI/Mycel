from __future__ import annotations

import os

from fastapi import Request

from backend.bootstrap.app_entrypoint import resolve_app_port


def resolve_monitor_evaluation_base_url(request: Request) -> str:
    explicit = os.getenv("LEON_MONITOR_EVALUATION_BASE_URL")
    if explicit:
        return explicit.rstrip("/")

    if getattr(request.app, "title", "") != "Mycel Monitor Backend":
        return str(request.base_url).rstrip("/")

    backend_port = resolve_app_port("LEON_BACKEND_PORT", "worktree.ports.backend", 8001)
    hostname = getattr(request.url, "hostname", None) or "127.0.0.1"
    scheme = getattr(request.url, "scheme", "http")
    if hostname in {"127.0.0.1", "localhost", "testserver"}:
        return f"{scheme}://127.0.0.1:{backend_port}"

    raise RuntimeError("LEON_MONITOR_EVALUATION_BASE_URL is required for standalone monitor execution targeting")
