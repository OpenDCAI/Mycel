"""Sandbox runtime read-source boundary for Monitor."""

from __future__ import annotations

from typing import Any

from storage.runtime import build_sandbox_monitor_repo as make_sandbox_monitor_repo


def list_sandbox_rows() -> list[dict[str, Any]]:
    repo = make_sandbox_monitor_repo()
    try:
        return repo.query_sandboxes()
    finally:
        repo.close()


def load_sandbox_detail_rows(sandbox_id: str) -> dict[str, Any]:
    repo = make_sandbox_monitor_repo()
    try:
        sandbox = repo.query_sandbox(sandbox_id)
        if sandbox is None:
            raise KeyError(f"Sandbox not found: {sandbox_id}")
        return {
            "sandbox": sandbox,
            "cleanup_target": repo.query_sandbox_cleanup_target(sandbox_id) or {},
            "threads": repo.query_sandbox_threads(sandbox_id),
            "runtime_rows": repo.query_sandbox_runtime_rows(sandbox_id),
            "runtime_id": repo.query_sandbox_instance_id(sandbox_id),
        }
    finally:
        repo.close()


def load_sandbox_cleanup_target(sandbox_id: str) -> dict[str, Any]:
    repo = make_sandbox_monitor_repo()
    try:
        sandbox = repo.query_sandbox(sandbox_id)
        cleanup_target = repo.query_sandbox_cleanup_target(sandbox_id) or {}
    finally:
        repo.close()

    if sandbox is None:
        raise KeyError(f"Sandbox not found: {sandbox_id}")
    return cleanup_target
