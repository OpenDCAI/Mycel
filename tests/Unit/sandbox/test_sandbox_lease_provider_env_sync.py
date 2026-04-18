import uuid
from pathlib import Path

import sandbox.lease as sandbox_lease_module
from sandbox.lease import SandboxInstance, SQLiteLease


class _FakeLeaseRepo:
    def __init__(self, row):
        self.row = row
        self.observe_calls = []
        self.closed = False

    def observe_status(self, *, lease_id: str, status: str, observed_at=None):
        self.observe_calls.append(
            {
                "lease_id": lease_id,
                "status": status,
                "observed_at": observed_at,
            }
        )
        return dict(self.row)

    def close(self) -> None:
        self.closed = True


class _FakeAdoptLeaseRepo:
    def __init__(self, row):
        self.row = row
        self.adopt_calls = []
        self.get_calls = []
        self.closed = False

    def get(self, lease_id: str):
        self.get_calls.append(lease_id)
        return {
            "lease_id": "lease-1",
            "provider_name": "local",
            "recipe_id": None,
            "recipe_json": None,
            "workspace_key": None,
            "current_instance_id": None,
            "instance_created_at": None,
            "desired_state": "running",
            "observed_state": "detached",
            "instance_status": "detached",
            "version": 1,
            "observed_at": "2026-04-17T00:00:00+00:00",
            "last_error": None,
            "needs_refresh": 0,
            "refresh_hint_at": None,
            "status": "active",
            "volume_id": None,
            "created_at": "2026-04-17T00:00:00+00:00",
            "updated_at": "2026-04-17T00:00:00+00:00",
            "_instance": None,
        }

    def adopt_instance(self, *, lease_id: str, provider_name: str, instance_id: str, status: str = "unknown"):
        self.adopt_calls.append(
            {
                "lease_id": lease_id,
                "provider_name": provider_name,
                "instance_id": instance_id,
                "status": status,
            }
        )
        return dict(self.row)

    def close(self) -> None:
        self.closed = True


class _FakeEventRepo:
    def __init__(self) -> None:
        self.closed = False

    def record(self, **_kwargs) -> None:
        return None

    def close(self) -> None:
        self.closed = True


class _FakeSandboxRepo:
    def __init__(self) -> None:
        self.binding_updates = []
        self.observed_state_updates = []
        self.closed = False

    def update_runtime_binding(self, *, sandbox_id: str, provider_env_id: str | None, updated_at: str) -> None:
        self.binding_updates.append(
            {
                "sandbox_id": sandbox_id,
                "provider_env_id": provider_env_id,
                "updated_at": updated_at,
            }
        )

    def update_observed_state(self, *, sandbox_id: str, observed_state: str, updated_at: str) -> None:
        self.observed_state_updates.append(
            {
                "sandbox_id": sandbox_id,
                "observed_state": observed_state,
                "updated_at": updated_at,
            }
        )

    def close(self) -> None:
        self.closed = True


class _FakeProvider:
    name = "local"

    class _Capability:
        supports_status_probe = False

    def get_capability(self):
        return self._Capability()

    def create_session(self, *, context_id: str, thread_id=None):
        return type("SessionInfo", (), {"session_id": "inst-created"})()


def test_observe_status_detached_clears_sandbox_provider_env(monkeypatch) -> None:
    fake_lease_repo = _FakeLeaseRepo(
        {
            "lease_id": "lease-1",
            "provider_name": "local",
            "recipe_id": None,
            "recipe_json": None,
            "workspace_key": None,
            "current_instance_id": None,
            "instance_created_at": None,
            "desired_state": "running",
            "observed_state": "detached",
            "instance_status": "detached",
            "version": 2,
            "observed_at": "2026-04-17T00:00:05+00:00",
            "last_error": None,
            "needs_refresh": 0,
            "refresh_hint_at": None,
            "status": "expired",
            "volume_id": None,
            "created_at": "2026-04-17T00:00:00+00:00",
            "updated_at": "2026-04-17T00:00:05+00:00",
            "_instance": None,
        }
    )
    fake_event_repo = _FakeEventRepo()
    fake_sandbox_repo = _FakeSandboxRepo()

    monkeypatch.setattr(sandbox_lease_module, "_use_supabase_storage", lambda _db_path=None: True)
    monkeypatch.setattr(sandbox_lease_module, "_make_lease_repo", lambda _db_path=None: fake_lease_repo)
    monkeypatch.setattr(sandbox_lease_module, "_make_provider_event_repo", lambda: fake_event_repo)
    monkeypatch.setattr(sandbox_lease_module, "_make_sandbox_repo", lambda: fake_sandbox_repo)

    lease = SQLiteLease(
        lease_id="lease-1",
        provider_name="local",
        current_instance=SandboxInstance(
            instance_id="inst-1",
            provider_name="local",
            status="running",
            created_at=sandbox_lease_module.utc_now(),
        ),
        db_path=Path("/tmp/fake-sandbox.db"),
        observed_state="running",
        status="active",
    )

    lease._observe_status_via_strategy_repo("detached", source="test")

    assert fake_sandbox_repo.binding_updates == [
        {
            "sandbox_id": f"sandbox-{uuid.uuid5(uuid.NAMESPACE_URL, 'mycel-runtime:lease-1').hex}",
            "provider_env_id": None,
            "updated_at": "2026-04-17T00:00:05+00:00",
        }
    ]
    assert fake_sandbox_repo.observed_state_updates == [
        {
            "sandbox_id": f"sandbox-{uuid.uuid5(uuid.NAMESPACE_URL, 'mycel-runtime:lease-1').hex}",
            "observed_state": "detached",
            "updated_at": "2026-04-17T00:00:05+00:00",
        }
    ]


def test_ensure_active_instance_sets_sandbox_provider_env_from_adopted_instance(monkeypatch) -> None:
    fake_lease_repo = _FakeAdoptLeaseRepo(
        {
            "lease_id": "lease-1",
            "provider_name": "local",
            "recipe_id": None,
            "recipe_json": None,
            "workspace_key": None,
            "current_instance_id": "inst-created",
            "instance_created_at": "2026-04-17T00:00:05+00:00",
            "desired_state": "running",
            "observed_state": "running",
            "instance_status": "running",
            "version": 2,
            "observed_at": "2026-04-17T00:00:05+00:00",
            "last_error": None,
            "needs_refresh": 0,
            "refresh_hint_at": None,
            "status": "active",
            "volume_id": None,
            "created_at": "2026-04-17T00:00:00+00:00",
            "updated_at": "2026-04-17T00:00:05+00:00",
            "_instance": {
                "instance_id": "inst-created",
                "lease_id": "lease-1",
                "provider_session_id": "inst-created",
                "status": "running",
                "created_at": "2026-04-17T00:00:05+00:00",
                "last_seen_at": "2026-04-17T00:00:05+00:00",
            },
        }
    )
    fake_sandbox_repo = _FakeSandboxRepo()

    monkeypatch.setattr(sandbox_lease_module, "_use_supabase_storage", lambda _db_path=None: True)
    monkeypatch.setattr(sandbox_lease_module, "_make_lease_repo", lambda _db_path=None: fake_lease_repo)
    monkeypatch.setattr(sandbox_lease_module, "_make_sandbox_repo", lambda: fake_sandbox_repo)
    monkeypatch.setattr(sandbox_lease_module, "_make_provider_event_repo", lambda: _FakeEventRepo())

    lease = SQLiteLease(
        lease_id="lease-1",
        provider_name="local",
        db_path=Path("/tmp/fake-sandbox.db"),
        observed_state="detached",
        status="active",
    )

    instance = lease.ensure_active_instance(_FakeProvider())

    assert instance.instance_id == "inst-created"
    assert fake_sandbox_repo.binding_updates == [
        {
            "sandbox_id": f"sandbox-{uuid.uuid5(uuid.NAMESPACE_URL, 'mycel-runtime:lease-1').hex}",
            "provider_env_id": "inst-created",
            "updated_at": "2026-04-17T00:00:05+00:00",
        }
    ]
