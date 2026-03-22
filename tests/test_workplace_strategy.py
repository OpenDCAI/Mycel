"""Unit tests for SandboxManager._resolve_workplace strategy gate."""
import tempfile
import uuid
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from sandbox.manager import SandboxManager
from sandbox.provider import (
    MountCapability,
    Metrics,
    ProviderCapability,
    ProviderExecResult,
    SandboxProvider,
    SessionInfo,
)


class FakeWorkplaceProvider(SandboxProvider):
    """Provider with supports_workplace=True for strategy gate tests."""

    name = "fake-wp"
    WORKSPACE_ROOT = "/workspace"

    def __init__(self):
        self._created_workplaces: list[tuple[str, str]] = []

    def get_capability(self) -> ProviderCapability:
        return ProviderCapability(
            can_pause=True,
            can_resume=True,
            can_destroy=True,
            mount=MountCapability(supports_workplace=True),
        )

    def create_workplace(self, member_id: str, mount_path: str) -> str:
        ref = f"vol-{member_id}"
        self._created_workplaces.append((member_id, mount_path))
        return ref

    def create_session(self, context_id=None, thread_id=None):
        return SessionInfo(session_id=f"s-{uuid.uuid4().hex[:8]}", provider=self.name, status="running")

    def destroy_session(self, session_id, sync=True):
        return True

    def pause_session(self, session_id):
        return True

    def resume_session(self, session_id):
        return True

    def get_session_status(self, session_id):
        return "running"

    def execute(self, session_id, command, timeout_ms=30000, cwd=None):
        return ProviderExecResult(output="", exit_code=0)

    def read_file(self, session_id, path):
        return ""

    def write_file(self, session_id, path, content):
        return "ok"

    def list_dir(self, session_id, path):
        return []

    def get_metrics(self, session_id):
        return None

    def create_runtime(self, terminal, lease):
        from sandbox.runtime import RemoteWrappedRuntime
        return RemoteWrappedRuntime(terminal, lease, self)


class FakeNoWorkplaceProvider(FakeWorkplaceProvider):
    """Provider with supports_workplace=False."""

    name = "fake-no-wp"

    def get_capability(self) -> ProviderCapability:
        return ProviderCapability(
            can_pause=True,
            can_resume=True,
            can_destroy=True,
            mount=MountCapability(supports_workplace=False),
        )


def _make_manager(provider, tmp_path):
    db = Path(tmp_path) / "test.db"
    return SandboxManager(provider=provider, db_path=db)


def test_resolve_workplace_no_member():
    """No member_id in thread config → returns None (File Channel)."""
    with tempfile.TemporaryDirectory() as td:
        mgr = _make_manager(FakeWorkplaceProvider(), td)
        with patch("backend.web.utils.helpers.load_thread_config", return_value=None, create=True):
            result = mgr._resolve_workplace("thread-no-member")
        assert result is None


def test_resolve_workplace_provider_unsupported():
    """Provider without supports_workplace → returns None."""
    with tempfile.TemporaryDirectory() as td:
        mgr = _make_manager(FakeNoWorkplaceProvider(), td)
        result = mgr._resolve_workplace("thread-1", member_id="m_abc123")
        assert result is None


def test_resolve_workplace_existing():
    """Existing workplace → returns it without creating."""
    existing = {
        "member_id": "m_abc123",
        "provider_type": "fake-wp",
        "backend_ref": "vol-m_abc123",
        "mount_path": "/workspace/files",
    }
    with tempfile.TemporaryDirectory() as td:
        provider = FakeWorkplaceProvider()
        mgr = _make_manager(provider, td)
        with patch("backend.web.services.workspace_service.get_agent_workplace", return_value=existing, create=True):
            result = mgr._resolve_workplace("thread-1", member_id="m_abc123")
        assert result == existing
        assert provider._created_workplaces == []  # no new workplace created


def test_resolve_workplace_lazy_create():
    """No existing workplace → creates one via provider and persists to DB."""
    with tempfile.TemporaryDirectory() as td:
        provider = FakeWorkplaceProvider()
        mgr = _make_manager(provider, td)
        expected = {
            "member_id": "m_abc123",
            "provider_type": "fake-wp",
            "backend_ref": "vol-m_abc123",
            "mount_path": "/workspace/files",
        }
        with patch("backend.web.services.workspace_service.get_agent_workplace", return_value=None, create=True):
            with patch("backend.web.services.workspace_service.create_agent_workplace", return_value=expected, create=True) as mock_create:
                result = mgr._resolve_workplace("thread-1", member_id="m_abc123")
        assert result == expected
        assert len(provider._created_workplaces) == 1
        assert provider._created_workplaces[0][0] == "m_abc123"
        mock_create.assert_called_once()
