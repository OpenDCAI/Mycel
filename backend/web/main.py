"""Leon Web Backend - FastAPI Application."""

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


def _ensure_windows_db_env_defaults() -> None:
    """On Windows, default Leon DBs to a LOCALAPPDATA-backed path."""
    if sys.platform != "win32":
        return

    root = _resolve_windows_db_root()
    root.mkdir(parents=True, exist_ok=True)
    defaults = {
        "LEON_DB_PATH": root / "leon.db",
        "LEON_RUN_EVENT_DB_PATH": root / "events.db",
        "LEON_QUEUE_DB_PATH": root / "queue.db",
        "LEON_CHAT_DB_PATH": root / "chat.db",
        "LEON_SANDBOX_DB_PATH": root / "sandbox.db",
        "LEON_SUBAGENT_DB_PATH": root / "subagent.db",
        "LEON_EVAL_DB_PATH": root / "eval.db",
    }
    for key, value in defaults.items():
        os.environ.setdefault(key, str(value))


def _resolve_windows_db_root() -> Path:
    local_appdata = Path(os.getenv("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
    candidates = [
        local_appdata / "Leon",
        Path.home() / ".codex" / "memories" / "mycel-run",
        Path.home() / ".leon-win",
    ]
    seen: set[Path] = set()
    for root in candidates:
        if root in seen:
            continue
        seen.add(root)
        if _sqlite_root_supports_wal(root):
            return root
    return candidates[0]


def _sqlite_root_supports_wal(root: Path) -> bool:
    probe = root / ".leon-probe.db"
    conn: sqlite3.Connection | None = None
    try:
        root.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(probe), timeout=1.0)
        mode = conn.execute("PRAGMA journal_mode=WAL").fetchone()
        conn.execute("CREATE TABLE IF NOT EXISTS _probe(x INTEGER)")
        conn.commit()
        return bool(mode and str(mode[0]).lower() == "wal")
    except Exception:
        return False
    finally:
        if conn is not None:
            conn.close()
        for suffix in ("", "-wal", "-shm"):
            try:
                (root / f".leon-probe.db{suffix}").unlink(missing_ok=True)
            except OSError:
                pass


_ensure_windows_db_env_defaults()

from backend.web.core.lifespan import lifespan  # noqa: E402
from backend.web.routers import (  # noqa: E402
    auth,
    connections,
    contacts,
    debug,
    entities,
    marketplace,
    monitor,
    panel,
    sandbox,
    settings,
    thread_files,
    threads,
    webhooks,
)
from backend.web.routers import messaging as messaging_router  # noqa: E402
from messaging.relationships.router import router as relationships_router  # noqa: E402

# Create FastAPI app
app = FastAPI(title="Leon Web Backend", lifespan=lifespan)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router)
app.include_router(threads.router)
app.include_router(messaging_router.router)
app.include_router(contacts.router)
app.include_router(relationships_router)
app.include_router(entities.router)
app.include_router(entities.members_router)
app.include_router(sandbox.router)
app.include_router(webhooks.router)
app.include_router(connections.router)
app.include_router(thread_files.router)
app.include_router(thread_files._public)
app.include_router(settings.router)
app.include_router(debug.router)
app.include_router(panel.router)
app.include_router(monitor.router)
app.include_router(marketplace.router)


def _resolve_port() -> int:
    """Resolve backend port: env var > git worktree config > default 8001."""
    port = os.environ.get("LEON_BACKEND_PORT") or os.environ.get("PORT")
    if port:
        return int(port)
    try:
        result = subprocess.run(
            ["git", "config", "--worktree", "--get", "worktree.ports.backend"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if result.returncode == 0 and result.stdout.strip():
            return int(result.stdout.strip())
    except (subprocess.TimeoutExpired, ValueError, FileNotFoundError):
        pass
    return 8001


if __name__ == "__main__":
    # @@@port-precedence - git worktree config > LEON_BACKEND_PORT > PORT > 8001
    port = _resolve_port()
    # @@@module-launch-target - Package-qualified target keeps module launch (`python -m backend.web.main`) import-safe.
    # @@@reload-dirs - restrict file watching to backend + core + config + storage only.
    # Without this, StatReload scans .venv/, node_modules/, .git/ etc. and burns 50-80% CPU.
    uvicorn.run(
        "backend.web.main:app",
        host="0.0.0.0",
        port=port,
        reload=True,
        reload_dirs=["backend", "core", "config", "storage", "sandbox"],
    )
