import inspect

import pytest

import storage.providers.supabase.lease_repo as lease_repo_module
from storage.providers.supabase.lease_repo import SupabaseLeaseRepo
from tests.fakes.supabase import FakeSupabaseClient


class _RejectBareSandboxLeasesClient(FakeSupabaseClient):
    def table(self, table_name: str):
        if table_name == "sandbox_leases":
            raise AssertionError("staging sandbox_leases should not be accessed")
        return super().table(table_name)


def _client(tables: dict[str, list[dict]] | None = None) -> _RejectBareSandboxLeasesClient:
    return _RejectBareSandboxLeasesClient(tables={} if tables is None else tables)


def test_supabase_lease_repo_names_container_bridge_without_adapter_label():
    source = inspect.getsource(SupabaseLeaseRepo)
    stale_adapter_label = "Lease-" + "compatible adapter"

    assert stale_adapter_label not in source
    assert "Container-backed LeaseRepo bridge" in source


def test_supabase_lease_repo_internal_bridge_state_not_named_as_compat_helper():
    source = inspect.getsource(lease_repo_module)
    stale_helper = "def _" + "compat("
    stale_local_name = "compat " + "="

    assert stale_helper not in source
    assert stale_local_name not in source


def _sandbox_row(
    *,
    sandbox_id: str = "sandbox-1",
    lease_id: str = "lease-1",
    provider_env_id: str | None = "inst-1",
    observed_state: str = "running",
    status: str = "ready",
    lease_status: str = "active",
    version: int = 2,
    needs_refresh: int = 1,
    refresh_hint_at: str | None = "2026-04-07T00:00:06+00:00",
    instance_created_at: str | None = "2026-04-07T00:00:01+00:00",
) -> dict:
    return {
        "id": sandbox_id,
        "owner_user_id": "owner-1",
        "provider_name": "local",
        "provider_env_id": provider_env_id,
        "sandbox_template_id": "local:default",
        "desired_state": "running",
        "observed_state": observed_state,
        "status": status,
        "observed_at": "2026-04-07T00:00:05+00:00",
        "last_error": None,
        "config": {
            "legacy_lease_id": lease_id,
            "lease_compat": {
                "recipe_id": "local:default",
                "recipe_json": '{"id":"local:default"}',
                "workspace_key": None,
                "version": version,
                "needs_refresh": needs_refresh,
                "refresh_hint_at": refresh_hint_at,
                "instance_created_at": instance_created_at,
                "status": lease_status,
            },
        },
        "created_at": "2026-04-07T00:00:00+00:00",
        "updated_at": "2026-04-07T00:00:05+00:00",
    }


def test_supabase_lease_repo_get_reads_container_sandboxes_lease_bridge():
    repo = SupabaseLeaseRepo(client=_client({"container.sandboxes": [_sandbox_row()]}))

    lease = repo.get("lease-1")

    assert lease is not None
    assert lease["sandbox_id"] == "sandbox-1"
    assert lease["lease_id"] == "lease-1"
    assert lease["provider_name"] == "local"
    assert lease["recipe_id"] == "local:default"
    assert lease["recipe_json"] == '{"id":"local:default"}'
    assert lease["current_instance_id"] == "inst-1"
    assert lease["instance_created_at"] == "2026-04-07T00:00:01+00:00"
    assert lease["version"] == 2
    assert lease["needs_refresh"] == 1
    assert lease["refresh_hint_at"] == "2026-04-07T00:00:06+00:00"
    assert lease["_instance"]["instance_id"] == "inst-1"


def test_supabase_lease_repo_create_requires_owner_user_id():
    repo = SupabaseLeaseRepo(client=_client())

    with pytest.raises(RuntimeError, match="requires owner_user_id"):
        repo.create("lease-1", "local")


def test_supabase_lease_repo_get_fails_loudly_when_lease_compat_not_backfilled():
    row = _sandbox_row()
    row["config"].pop("lease_compat")
    repo = SupabaseLeaseRepo(client=_client({"container.sandboxes": [row]}))

    with pytest.raises(RuntimeError, match="missing config.lease_compat"):
        repo.get("lease-1")


def test_supabase_lease_repo_provider_list_ignores_stale_bridge_shells_without_lease_compat():
    stale = _sandbox_row(sandbox_id="sandbox-stale", lease_id="lease-stale")
    stale["config"].pop("lease_compat")
    repo = SupabaseLeaseRepo(client=_client({"container.sandboxes": [_sandbox_row(), stale]}))

    leases = repo.list_by_provider("local")

    assert [lease["lease_id"] for lease in leases] == ["lease-1"]
    with pytest.raises(RuntimeError, match="missing config.lease_compat"):
        repo.get("lease-stale")


def test_supabase_lease_repo_create_writes_container_sandbox_bridge():
    tables: dict[str, list[dict]] = {}
    repo = SupabaseLeaseRepo(client=_client(tables))

    created = repo.create(
        "lease-1",
        "local",
        recipe_id="local:default",
        recipe_json='{"id":"local:default"}',
        owner_user_id="owner-1",
    )

    row = tables["container.sandboxes"][0]
    assert created["sandbox_id"] == row["id"]
    assert created["lease_id"] == "lease-1"
    assert row["owner_user_id"] == "owner-1"
    assert row["provider_name"] == "local"
    assert row["sandbox_template_id"] == "local:default"
    assert row["observed_state"] == "running"
    assert row["status"] == "ready"
    assert row["config"]["legacy_lease_id"] == "lease-1"
    assert row["config"]["lease_compat"]["recipe_json"] == '{"id":"local:default"}'
    assert row["config"]["lease_compat"]["needs_refresh"] == 0
    assert "volume_id" not in row


def test_supabase_lease_repo_adopt_instance_updates_container_runtime_fields_and_bridge_state():
    tables = {"container.sandboxes": [_sandbox_row(provider_env_id=None, observed_state="detached", version=0, needs_refresh=0)]}
    repo = SupabaseLeaseRepo(client=_client(tables))

    updated = repo.adopt_instance(
        lease_id="lease-1",
        provider_name="local",
        instance_id="inst-1",
        status="running",
    )

    row = tables["container.sandboxes"][0]
    assert row["provider_env_id"] == "inst-1"
    assert row["observed_state"] == "running"
    assert row["config"]["lease_compat"]["version"] == 1
    assert row["config"]["lease_compat"]["needs_refresh"] == 1
    assert updated["_instance"]["instance_id"] == "inst-1"


def test_supabase_lease_repo_persist_metadata_updates_container_and_bridge_state_fields():
    tables = {"container.sandboxes": [_sandbox_row(provider_env_id=None, observed_state="detached", version=0, needs_refresh=0)]}
    repo = SupabaseLeaseRepo(client=_client(tables))

    updated = repo.persist_metadata(
        lease_id="lease-1",
        recipe_id="local:python",
        recipe_json='{"id":"local:python"}',
        desired_state="running",
        observed_state="unknown",
        version=3,
        observed_at="2026-04-07T00:00:05+00:00",
        last_error="provider boom",
        needs_refresh=True,
        refresh_hint_at="2026-04-07T00:00:06+00:00",
        status="recovering",
    )

    row = tables["container.sandboxes"][0]
    bridge_state = row["config"]["lease_compat"]
    assert updated["lease_id"] == "lease-1"
    assert row["sandbox_template_id"] == "local:python"
    assert row["observed_state"] == "unknown"
    assert row["last_error"] == "provider boom"
    assert bridge_state["recipe_json"] == '{"id":"local:python"}'
    assert bridge_state["version"] == 3
    assert bridge_state["needs_refresh"] == 1
    assert bridge_state["refresh_hint_at"] == "2026-04-07T00:00:06+00:00"
    assert bridge_state["status"] == "recovering"


def test_supabase_lease_repo_observe_status_detaches_instance_from_container_sandbox():
    tables = {"container.sandboxes": [_sandbox_row()]}
    repo = SupabaseLeaseRepo(client=_client(tables))

    updated = repo.observe_status(
        lease_id="lease-1",
        status="detached",
        observed_at="2026-04-07T00:00:05+00:00",
    )

    row = tables["container.sandboxes"][0]
    bridge_state = row["config"]["lease_compat"]
    assert updated["lease_id"] == "lease-1"
    assert row["provider_env_id"] is None
    assert row["observed_state"] == "detached"
    assert bridge_state["status"] == "expired"
    assert bridge_state["needs_refresh"] == 0
    assert bridge_state["refresh_hint_at"] is None
    assert bridge_state["instance_created_at"] is None
    assert updated["_instance"] is None


def test_supabase_lease_repo_mark_needs_refresh_updates_bridge_state_only():
    tables = {"container.sandboxes": [_sandbox_row(needs_refresh=0, refresh_hint_at=None)]}
    repo = SupabaseLeaseRepo(client=_client(tables))

    assert repo.mark_needs_refresh("lease-1", hint_at="2026-04-07T00:00:06+00:00") is True

    bridge_state = tables["container.sandboxes"][0]["config"]["lease_compat"]
    assert bridge_state["needs_refresh"] == 1
    assert bridge_state["refresh_hint_at"] == "2026-04-07T00:00:06+00:00"


def test_supabase_lease_repo_delete_removes_container_sandbox_bridge():
    tables = {"container.sandboxes": [_sandbox_row()]}
    repo = SupabaseLeaseRepo(client=_client(tables))

    repo.delete("lease-1")

    assert tables["container.sandboxes"] == []
