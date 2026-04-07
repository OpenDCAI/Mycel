"""Pytest configuration for Leon tests.

Ensures the project root is in sys.path so imports work correctly.
"""

import gc
import sys
import time
from collections.abc import AsyncIterator, Generator
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

# Add project root to sys.path
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))


def _unlink_db(db_path: Path) -> None:
    """Delete a SQLite database file safely on all platforms.

    On Windows, sqlite3 connections hold OS-level file locks. Force GC to
    release any lingering connection objects, delete WAL/SHM auxiliary files,
    then retry the main file deletion a few times before giving up.
    """
    gc.collect()
    for wal_suffix in ("-wal", "-shm"):
        Path(str(db_path) + wal_suffix).unlink(missing_ok=True)
    if sys.platform == "win32":
        for _attempt in range(5):
            try:
                db_path.unlink(missing_ok=True)
                return
            except PermissionError:
                time.sleep(0.1)
                gc.collect()
        db_path.unlink(missing_ok=True)  # final attempt; raises if still locked
    else:
        db_path.unlink(missing_ok=True)


@pytest.fixture
def temp_db(tmp_path: Path) -> Generator[Path, None, None]:
    """Provide a temporary SQLite database path with Windows-safe cleanup."""
    db_path = tmp_path / "test.db"
    yield db_path
    _unlink_db(db_path)


class _FakeAsyncCursor:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, _query: str, *_args, **_kwargs) -> None:
        return None

    async def fetchone(self):
        return (1,)


class _FakeAsyncConnection:
    def cursor(self) -> _FakeAsyncCursor:
        return _FakeAsyncCursor()

    async def close(self) -> None:
        return None


@pytest.fixture(autouse=True)
def _stub_web_checkpointer_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep TestClient startup on the happy path unless a test overrides it."""
    from backend.web.core import lifespan as lifespan_module

    async def _connect(_dsn: str) -> _FakeAsyncConnection:
        return _FakeAsyncConnection()

    monkeypatch.setenv("LEON_POSTGRES_URL", "postgresql://tests")
    monkeypatch.setattr(lifespan_module, "AsyncConnection", SimpleNamespace(connect=_connect))


@pytest.fixture(autouse=True)
def _route_smoke_app_harness(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    path = str(request.node.path)
    if not path.endswith("tests/Integration/test_monitor_resources_route.py") and not path.endswith(
        "tests/Integration/test_resources_route.py"
    ):
        yield
        return

    from backend.web.core.dependencies import get_current_user_id
    from backend.web.main import app as web_app
    from backend.web.routers import monitor as monitor_router
    from backend.web.services import monitor_service, resource_projection_service

    @asynccontextmanager
    async def _noop_lifespan(_app) -> AsyncIterator[None]:
        yield

    product_payload = {
        "summary": {
            "snapshot_at": "now",
            "total_providers": 1,
            "active_providers": 1,
            "unavailable_providers": 0,
            "running_sessions": 1,
            "last_refreshed_at": "now",
            "refresh_status": "fresh",
        },
        "providers": [{"id": "local", "sessions": []}],
    }
    monitor_payload = {
        "summary": {
            "snapshot_at": "now",
            "running_sessions": 1,
            "last_refreshed_at": "now",
            "refresh_status": "fresh",
        },
        "providers": [{"id": "local"}],
    }
    lease_payload = {
        "summary": {"total": 1, "healthy": 1, "diverged": 0, "orphan": 0, "orphan_diverged": 0},
        "groups": [],
        "triage": {
            "summary": {
                "total": 1,
                "active_drift": 0,
                "detached_residue": 0,
                "orphan_cleanup": 0,
                "healthy_capacity": 1,
            },
            "groups": [],
        },
    }

    original_lifespan = web_app.router.lifespan_context
    monkeypatch.setattr(web_app.router, "lifespan_context", _noop_lifespan)
    web_app.dependency_overrides[get_current_user_id] = lambda: "user-test"
    monkeypatch.setattr(monitor_router, "get_monitor_resource_overview_snapshot", lambda: monitor_payload)
    monkeypatch.setattr(monitor_router, "refresh_monitor_resource_overview_sync", lambda: monitor_payload)
    monkeypatch.setattr(monitor_router, "list_leases", lambda: lease_payload)
    monkeypatch.setattr(monitor_router, "list_evaluations", lambda *args, **kwargs: {"items": []})
    monkeypatch.setattr(
        monitor_service,
        "runtime_health_snapshot",
        lambda: {
            "snapshot_at": "now",
            "db": {"counts": {"chat_sessions": 1}},
            "sessions": {"total": 1},
        },
    )
    monkeypatch.setattr(
        resource_projection_service,
        "list_user_resource_providers",
        lambda *_args, **_kwargs: product_payload,
    )
    try:
        yield
    finally:
        web_app.router.lifespan_context = original_lifespan
        web_app.dependency_overrides.clear()
