import json
from pathlib import Path
from unittest.mock import MagicMock

from backend.web.services import resource_service
from sandbox.provider import ProviderCapability, build_resource_capabilities


def _write_provider_config(tmp_path: Path, instance_name: str, payload: dict) -> None:
    (tmp_path / f"{instance_name}.json").write_text(json.dumps(payload))


def _make_fake_thread_config_repo(agent_by_thread: dict[str, str]):
    """Fake ThreadConfigRepo backed by a simple dict — works for both SQLite and Supabase code paths."""
    repo = MagicMock()
    repo.lookup_config.side_effect = lambda tid: (
        {"sandbox_type": "local", "cwd": None, "model": None, "queue_mode": None,
         "observation_provider": None, "agent": agent_by_thread[tid]}
        if tid in agent_by_thread else None
    )
    repo.close.return_value = None
    return repo


def _make_fake_repo(sessions: list[dict]):
    """Create a mock repo that returns pre-canned sessions."""
    repo = MagicMock()
    repo.list_sessions_with_leases.return_value = sessions
    repo.close.return_value = None
    return repo


def _patch_resources_context(
    monkeypatch,
    *,
    tmp_path: Path,
    providers: list[dict],
    sessions: list[dict],
    snapshots: dict | None = None,
) -> None:
    monkeypatch.setattr(resource_service, "SANDBOXES_DIR", tmp_path)
    monkeypatch.setattr(resource_service, "available_sandbox_types", lambda: providers)
    monkeypatch.setattr(
        resource_service, "SQLiteSandboxMonitorRepo", lambda: _make_fake_repo(sessions),
    )
    capability_by_provider = {
        "local": build_resource_capabilities(
            filesystem=True, terminal=True, metrics=False, screenshot=False,
            web=False, process=False, hooks=False, snapshot=False,
        ),
        "docker": build_resource_capabilities(
            filesystem=True, terminal=True, metrics=True, screenshot=False,
            web=False, process=False, hooks=False, snapshot=False,
        ),
        "e2b": build_resource_capabilities(
            filesystem=True, terminal=True, metrics=False, screenshot=False,
            web=False, process=False, hooks=False, snapshot=True,
        ),
        "daytona": build_resource_capabilities(
            filesystem=True, terminal=True, metrics=False, screenshot=False,
            web=False, process=False, hooks=True, snapshot=False,
        ),
        "agentbay": build_resource_capabilities(
            filesystem=True, terminal=True, metrics=True, screenshot=True,
            web=True, process=True, hooks=False, snapshot=False,
        ),
    }

    def _fake_provider_builder(config_name: str, *, sandboxes_dir: Path | None = None):
        provider_name = resource_service.resolve_provider_name(
            config_name, sandboxes_dir=sandboxes_dir or tmp_path,
        )
        resource_capabilities = capability_by_provider.get(provider_name)
        if resource_capabilities is None:
            return None

        class _FakeProvider:
            def get_capability(self) -> ProviderCapability:
                return ProviderCapability(
                    can_pause=True, can_resume=True, can_destroy=True,
                    resource_capabilities=resource_capabilities,
                )

        return _FakeProvider()

    monkeypatch.setattr(resource_service, "build_provider_from_config_name", _fake_provider_builder)
    if snapshots is not None:
        monkeypatch.setattr(resource_service, "list_snapshots_by_lease_ids", lambda _: snapshots)


def test_list_resource_providers_maps_status_and_metric_metadata(tmp_path, monkeypatch):
    _write_provider_config(tmp_path, "docker_dev", {"provider": "docker"})

    monkeypatch.setattr(
        resource_service, "_make_thread_config_repo",
        lambda: _make_fake_thread_config_repo({"thread-local-1": "member-1"}),
    )
    monkeypatch.setattr(resource_service, "_member_name_map", lambda: {"member-1": "Alice"})
    _patch_resources_context(
        monkeypatch,
        tmp_path=tmp_path,
        providers=[
            {"name": "local", "available": True},
            {"name": "docker_dev", "available": False, "reason": "docker daemon down"},
        ],
        sessions=[
            {
                "provider": "local",
                "session_id": "sess-local-1",
                "thread_id": "thread-local-1",
                "observed_state": "detached",
                "desired_state": "running",
                "created_at": "2026-03-03T00:00:00",
            },
            {
                "provider": "docker_dev",
                "session_id": "sess-docker-1",
                "thread_id": "thread-docker-1",
                "observed_state": "paused",
                "desired_state": "paused",
                "created_at": "2026-03-03T00:00:00",
            },
        ],
    )

    payload = resource_service.list_resource_providers()
    assert "summary" in payload
    assert "providers" in payload
    assert payload["summary"]["total_providers"] == 2
    assert payload["summary"]["active_providers"] == 1
    assert payload["summary"]["unavailable_providers"] == 1
    assert payload["summary"]["running_sessions"] == 1

    local = next(item for item in payload["providers"] if item["id"] == "local")
    assert local["status"] == "active"
    assert local["telemetry"]["running"]["used"] == 1
    assert local["telemetry"]["running"]["source"] == "sandbox_db"
    assert local["telemetry"]["running"]["freshness"] == "cached"
    assert local["sessions"][0]["threadId"] == "thread-local-1"
    assert local["sessions"][0]["agentId"] == "member-1"
    assert local["sessions"][0]["agentName"] == "Alice"

    docker = next(item for item in payload["providers"] if item["id"] == "docker_dev")
    assert docker["status"] == "unavailable"
    assert docker["error"]["code"] == "PROVIDER_UNAVAILABLE"
    assert docker["sessions"][0]["status"] == "paused"
    assert docker["sessions"][0]["agentName"] == "未绑定Agent"


def test_list_resource_providers_marks_ready_when_no_running_sessions(tmp_path, monkeypatch):
    _write_provider_config(tmp_path, "e2b_test", {"provider": "e2b"})
    _patch_resources_context(
        monkeypatch,
        tmp_path=tmp_path,
        providers=[{"name": "e2b_test", "available": True}],
        sessions=[],
    )

    payload = resource_service.list_resource_providers()
    assert len(payload["providers"]) == 1
    assert payload["summary"]["active_providers"] == 0
    assert payload["summary"]["running_sessions"] == 0

    e2b = payload["providers"][0]
    assert e2b["id"] == "e2b_test"
    assert e2b["status"] == "ready"
    assert e2b["telemetry"]["running"]["used"] == 0
    assert e2b["telemetry"]["cpu"]["freshness"] == "stale"
    assert e2b["cardCpu"]["used"] is None
    assert e2b["cardCpu"]["limit"] is None
    assert e2b["cardCpu"]["error"] is not None


def test_list_resource_providers_prefers_config_console_url_override(tmp_path, monkeypatch):
    _write_provider_config(
        tmp_path,
        "daytona_selfhost",
        {
            "provider": "daytona",
            "console_url": "https://ops.example.com/daytona",
            "daytona": {"target": "local", "api_url": "https://daytona.example.com/api"},
        },
    )
    _patch_resources_context(
        monkeypatch,
        tmp_path=tmp_path,
        providers=[{"name": "daytona_selfhost", "available": True}],
        sessions=[],
    )

    payload = resource_service.list_resource_providers()
    provider = payload["providers"][0]
    assert provider["id"] == "daytona_selfhost"
    assert provider["consoleUrl"] == "https://ops.example.com/daytona"
    assert provider["type"] == "container"


def test_list_resource_providers_uses_snapshot_metrics(tmp_path, monkeypatch):
    _write_provider_config(tmp_path, "agentbay_prod", {"provider": "agentbay"})
    _patch_resources_context(
        monkeypatch,
        tmp_path=tmp_path,
        providers=[{"name": "agentbay_prod", "available": True}],
        sessions=[
            {
                "provider": "agentbay_prod",
                "session_id": "sess-1",
                "thread_id": "thread-1",
                "lease_id": "lease-1",
                "status": "running",
                "created_at": "2026-03-03T00:00:00",
            }
        ],
        snapshots={
            "lease-1": {
                "lease_id": "lease-1",
                "cpu_used": 21.0,
                "cpu_limit": 100.0,
                "memory_used_mb": 1024.0,
                "memory_total_mb": 4096.0,
                "disk_used_gb": 4.0,
                "disk_total_gb": 20.0,
                "collected_at": "2099-01-01T00:00:00Z",
            }
        },
    )

    payload = resource_service.list_resource_providers()
    provider = payload["providers"][0]
    assert provider["telemetry"]["cpu"]["used"] == 21.0
    assert provider["telemetry"]["cpu"]["limit"] == 100.0
    assert provider["telemetry"]["memory"]["used"] == 1.0
    assert provider["telemetry"]["memory"]["limit"] == 4.0
    assert provider["telemetry"]["disk"]["used"] == 4.0
    assert provider["telemetry"]["disk"]["limit"] == 20.0
    assert provider["telemetry"]["cpu"]["source"] == "api"


def test_list_resource_providers_surfaces_snapshot_probe_error(tmp_path, monkeypatch):
    _write_provider_config(tmp_path, "daytona_cloud", {"provider": "daytona"})
    _patch_resources_context(
        monkeypatch,
        tmp_path=tmp_path,
        providers=[{"name": "daytona_cloud", "available": True}],
        sessions=[
            {
                "provider": "daytona_cloud",
                "session_id": "sess-1",
                "thread_id": "thread-1",
                "lease_id": "lease-1",
                "status": "paused",
                "created_at": "2026-03-03T00:00:00",
            }
        ],
        snapshots={
            "lease-1": {
                "lease_id": "lease-1",
                "cpu_used": None,
                "cpu_limit": None,
                "memory_used_mb": None,
                "memory_total_mb": None,
                "disk_used_gb": None,
                "disk_total_gb": None,
                "probe_error": "metrics unavailable",
                "collected_at": "2099-01-01T00:00:00Z",
            }
        },
    )

    payload = resource_service.list_resource_providers()
    provider = payload["providers"][0]
    assert provider["telemetry"]["cpu"]["used"] is None
    assert provider["telemetry"]["cpu"]["source"] == "sandbox_db"
    assert provider["telemetry"]["cpu"]["error"] == "metrics unavailable"
    assert provider["telemetry"]["memory"]["error"] == "metrics unavailable"
    assert provider["telemetry"]["disk"]["error"] == "metrics unavailable"


def test_thread_owner_uses_agent_ref_as_name_when_member_lookup_missing(monkeypatch):
    monkeypatch.setattr(
        resource_service, "_make_thread_config_repo",
        lambda: _make_fake_thread_config_repo({"thread-1": "Lex"}),
    )
    monkeypatch.setattr(resource_service, "_member_name_map", lambda: {})

    owners = resource_service._thread_owners(["thread-1", "thread-2"])
    assert owners["thread-1"]["agent_id"] == "Lex"
    assert owners["thread-1"]["agent_name"] == "Lex"
    assert owners["thread-2"]["agent_id"] is None
    assert owners["thread-2"]["agent_name"] == "未绑定Agent"


def test_thread_owner_works_with_supabase_backed_thread_config(monkeypatch):
    """Thread config lookup routes through ThreadConfigRepo abstraction,
    so it works identically whether the backing store is SQLite or Supabase."""

    class _FakeSupabaseThreadConfigRepo:
        """Mimics SupabaseThreadConfigRepo interface without a real Supabase connection."""
        def __init__(self):
            self._data = {"thread-supabase-1": "agent-uuid-abc"}

        def lookup_config(self, thread_id: str):
            agent = self._data.get(thread_id)
            return {"sandbox_type": "local", "cwd": None, "model": None,
                    "queue_mode": None, "observation_provider": None, "agent": agent} if agent else None

        def close(self): pass

    monkeypatch.setattr(resource_service, "_make_thread_config_repo", _FakeSupabaseThreadConfigRepo)
    monkeypatch.setattr(resource_service, "_member_name_map", lambda: {"agent-uuid-abc": "Bob"})

    owners = resource_service._thread_owners(["thread-supabase-1", "thread-missing"])
    assert owners["thread-supabase-1"]["agent_id"] == "agent-uuid-abc"
    assert owners["thread-supabase-1"]["agent_name"] == "Bob"
    assert owners["thread-missing"]["agent_id"] is None
    assert owners["thread-missing"]["agent_name"] == "未绑定Agent"


def test_list_resource_providers_uses_instance_capability_single_source(tmp_path, monkeypatch):
    _write_provider_config(tmp_path, "agentbay_prod", {"provider": "agentbay"})
    _patch_resources_context(
        monkeypatch,
        tmp_path=tmp_path,
        providers=[{"name": "agentbay_prod", "available": True}],
        sessions=[],
    )

    class _InstanceOverrideProvider:
        def get_capability(self) -> ProviderCapability:
            return ProviderCapability(
                can_pause=False, can_resume=False, can_destroy=True,
                resource_capabilities=build_resource_capabilities(
                    filesystem=True, terminal=True, metrics=False, screenshot=False,
                    web=False, process=False, hooks=False, snapshot=False,
                ),
            )

    monkeypatch.setattr(
        resource_service,
        "build_provider_from_config_name",
        lambda _name, **_kwargs: _InstanceOverrideProvider(),
    )

    payload = resource_service.list_resource_providers()
    provider = payload["providers"][0]
    assert provider["capabilities"]["metrics"] is False
    assert provider["capabilities"]["web"] is False
