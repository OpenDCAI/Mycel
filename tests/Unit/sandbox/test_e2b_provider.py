"""Smoke test for E2B provider and sandbox."""

import builtins
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sandbox.providers.e2b import E2BProvider


def test_e2b_provider_requires_sdk(monkeypatch):
    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "e2b":
            raise ModuleNotFoundError("No module named 'e2b'")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(ModuleNotFoundError, match="No module named 'e2b'"):
        E2BProvider(api_key="test-key", timeout=60)


def test_e2b_create_session_bootstraps_workspace_files_dir(monkeypatch):
    calls: list[tuple[str, str | None, float | None]] = []

    class _FakeCommands:
        def run(self, command, cwd=None, timeout=None):
            calls.append((command, cwd, timeout))
            return SimpleNamespace(stdout="", stderr="", exit_code=0)

    class _FakeSandbox:
        def __init__(self):
            self.sandbox_id = "sbx-123"
            self.commands = _FakeCommands()

        @classmethod
        def beta_create(cls, template, timeout, auto_pause, api_key):
            return cls()

    monkeypatch.setitem(sys.modules, "e2b", SimpleNamespace(Sandbox=_FakeSandbox))

    provider = E2BProvider(api_key="test-key", timeout=60)
    info = provider.create_session()

    assert info.session_id == "sbx-123"
    assert calls == [("mkdir -p /home/user/workspace/files", "/home/user", 10.0)]


def test_e2b_provider():
    api_key = os.getenv("E2B_API_KEY")
    if not api_key or not api_key.startswith("e2b_"):
        print("E2B_API_KEY not set, skipping")
        return

    provider = E2BProvider(api_key=api_key, timeout=60)

    print("Creating session...")
    info = provider.create_session()
    print(f"  session_id: {info.session_id}")
    sid = info.session_id

    print("\nExecuting command...")
    result = provider.execute(sid, "echo hello && uname -a")
    print(f"  output: {result.output}")
    assert result.exit_code == 0

    print("\nWriting file...")
    provider.write_file(sid, "/home/user/test.txt", "hello from leon")

    print("\nReading file...")
    content = provider.read_file(sid, "/home/user/test.txt")
    print(f"  content: {content}")
    assert content == "hello from leon"

    print("\nListing /home/user...")
    items = provider.list_dir(sid, "/home/user")
    names = [i["name"] for i in items]
    print(f"  entries: {names}")
    assert "test.txt" in names

    print("\nChecking status...")
    status = provider.get_session_status(sid)
    print(f"  status: {status}")
    assert status == "running"

    print("\nPausing...")
    assert provider.pause_session(sid)

    status = provider.get_session_status(sid)
    print(f"  status after pause: {status}")
    assert status == "paused"

    print("\nResuming...")
    assert provider.resume_session(sid)

    content = provider.read_file(sid, "/home/user/test.txt")
    print(f"  content after resume: {content}")
    assert content == "hello from leon"

    print("\nDestroying...")
    assert provider.destroy_session(sid)

    print("\nAll tests passed!")


if __name__ == "__main__":
    test_e2b_provider()
