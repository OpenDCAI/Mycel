"""Shared helpers for Python app entrypoints."""

from __future__ import annotations

import os
import subprocess


def load_env_file_from_env() -> None:
    env_file = os.getenv("ENV_FILE")
    if not env_file:
        return

    from dotenv import load_dotenv

    load_dotenv(env_file, override=False)


def resolve_app_port(env_key: str, worktree_key: str, default_port: int) -> int:
    port = os.environ.get(env_key) or os.environ.get("PORT")
    if port:
        return int(port)
    try:
        result = subprocess.run(
            ["git", "config", "--worktree", "--get", worktree_key],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if result.returncode == 0 and result.stdout.strip():
            return int(result.stdout.strip())
    except (subprocess.TimeoutExpired, ValueError, FileNotFoundError):
        pass
    return default_port
