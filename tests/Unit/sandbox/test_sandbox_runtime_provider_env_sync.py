import uuid
from pathlib import Path

import sandbox.runtime_handle as sandbox_runtime_module
from sandbox.runtime_handle import SandboxInstance, SQLiteSandboxRuntimeHandle


class _FakeSandboxRuntimeRepo:
    def __init__(self, row):
        self.row = row
        self.observe_calls = []
        self.closed = False

    def observe_status(self, *, sandbox_runtime_id: str, status: str, observed_at=None):
        self.observe_calls.append(
            {
                "sandbox_runtime_id": sandbox_runtime_id,
                "status": status,
                "observed_at": observed_at,
            }
        )
        return dict(self.row)

    def close(self) -> None:
        self.closed = True


class _FakeAdoptSandboxRuntimeRepo:
    def __init__(self, row):
        self.row = row
        self.adopt_calls = []
        self.get_calls = []
        self.closed = False

    def get(self, sandbox_runtime_id: str):
        self.get_calls.append(sandbox_runtime_id)
        return {
            "sandbox_runtime_id": "runtime-1",
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

    def adopt_instance(
        self,
        *,
        sandbox_runtime_id: str,
        provider_name: str,
        instance_id: str,
        status: str = "unknown",
    ):
        self.adopt_calls.append(
            {
                "sandbox_runtime_id": sandbox_runtime_id,
                "provider_name": provider_name,
                "instance_id": instance_id,
                "status": status,
            }
        )
        return dict(self.row)

    def close(self) -> None:
        self.closed = True


class _FakeDestroySandboxRuntimeRepo:
    def __init__(self) -> None:
        self.closed = False
        self.persist_calls = []

    def _row(self, *, desired_state: str = "running", observed_state: str = "running", version: int = 1, instance=None):
        return {
            "sandbox_runtime_id": "runtime-1",
            "provider_name": "local",
            "recipe_id": None,
            "recipe_json": None,
            "workspace_key": None,
            "current_instance_id": instance["instance_id"] if instance else None,
            "instance_created_at": instance["created_at"] if instance else None,
            "desired_state": desired_state,
            "observed_state": observed_state,
            "instance_status": observed_state,
            "version": version,
            "observed_at": "2026-04-17T00:00:05+00:00",
            "last_error": None,
            "needs_refresh": 0,
            "refresh_hint_at": None,
            "status": "expired" if desired_state == "destroyed" else "active",
            "volume_id": None,
            "created_at": "2026-04-17T00:00:00+00:00",
            "updated_at": "2026-04-17T00:00:05+00:00",
            "_instance": instance,
        }

    def get(self, sandbox_runtime_id: str):
        assert sandbox_runtime_id == "runtime-1"
        return self._row(
            instance={
                "instance_id": "inst-1",
                "sandbox_runtime_id": "runtime-1",
                "provider_session_id": "inst-1",
                "status": "running",
                "created_at": "2026-04-17T00:00:01+00:00",
                "last_seen_at": "2026-04-17T00:00:05+00:00",
            }
        )

    def observe_status(self, *, sandbox_runtime_id: str, status: str, observed_at=None):
        assert sandbox_runtime_id == "runtime-1"
        assert status == "detached"
        return self._row(desired_state="running", observed_state="detached", version=2)

    def persist_metadata(self, **kwargs):
        self.persist_calls.append(kwargs)
        return self._row(desired_state="destroyed", observed_state="detached", version=3)

    def close(self) -> None:
        self.closed = True


class _FakeEventRepo:
    def __init__(self) -> None:
        self.closed = False

    def record(self, **_kwargs) -> None:
        return None

    def close(self) -> None:
        self.closed = True


class _StrictEventRepo:
    def __init__(self) -> None:
        self.calls = []
        self.closed = False

    def record(
        self,
        *,
        provider_name: str,
        instance_id: str,
        event_type: str,
        payload: dict,
        matched_runtime_handle: str | None,
        matched_sandbox_id: str | None,
    ) -> None:
        self.calls.append(
            {
                "provider_name": provider_name,
                "instance_id": instance_id,
                "event_type": event_type,
                "payload": payload,
                "matched_runtime_handle": matched_runtime_handle,
                "matched_sandbox_id": matched_sandbox_id,
            }
        )

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


class _FakeDestroyProvider:
    name = "local"

    class _Capability:
        can_destroy = True

    def __init__(self) -> None:
        self.destroyed = []

    def get_capability(self):
        return self._Capability()

    def destroy_session(self, instance_id: str) -> bool:
        self.destroyed.append(instance_id)
        return True


def test_observe_status_detached_clears_sandbox_provider_env(monkeypatch) -> None:
    fake_sandbox_runtime_repo = _FakeSandboxRuntimeRepo(
        {
            "sandbox_runtime_id": "runtime-1",
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

    monkeypatch.setattr(sandbox_runtime_module, "_use_supabase_storage", lambda _db_path=None: True)
    monkeypatch.setattr(sandbox_runtime_module, "_make_sandbox_runtime_repo", lambda _db_path=None: fake_sandbox_runtime_repo)
    monkeypatch.setattr(sandbox_runtime_module, "_make_provider_event_repo", lambda: fake_event_repo)
    monkeypatch.setattr(sandbox_runtime_module, "_make_sandbox_repo", lambda: fake_sandbox_repo)

    sandbox_runtime = SQLiteSandboxRuntimeHandle(
        sandbox_runtime_id="runtime-1",
        provider_name="local",
        current_instance=SandboxInstance(
            instance_id="inst-1",
            provider_name="local",
            status="running",
            created_at=sandbox_runtime_module.utc_now(),
        ),
        db_path=Path("/tmp/fake-sandbox.db"),
        observed_state="running",
        status="active",
    )

    sandbox_runtime._observe_status_via_strategy_repo("detached", source="test")

    assert fake_sandbox_repo.binding_updates == [
        {
            "sandbox_id": f"sandbox-{uuid.uuid5(uuid.NAMESPACE_URL, 'mycel-runtime:runtime-1').hex}",
            "provider_env_id": None,
            "updated_at": "2026-04-17T00:00:05+00:00",
        }
    ]
    assert fake_sandbox_repo.observed_state_updates == [
        {
            "sandbox_id": f"sandbox-{uuid.uuid5(uuid.NAMESPACE_URL, 'mycel-runtime:runtime-1').hex}",
            "observed_state": "detached",
            "updated_at": "2026-04-17T00:00:05+00:00",
        }
    ]


def test_ensure_active_instance_sets_sandbox_provider_env_from_adopted_instance(monkeypatch) -> None:
    fake_sandbox_runtime_repo = _FakeAdoptSandboxRuntimeRepo(
        {
            "sandbox_runtime_id": "runtime-1",
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
                "sandbox_runtime_id": "runtime-1",
                "provider_session_id": "inst-created",
                "status": "running",
                "created_at": "2026-04-17T00:00:05+00:00",
                "last_seen_at": "2026-04-17T00:00:05+00:00",
            },
        }
    )
    fake_sandbox_repo = _FakeSandboxRepo()

    monkeypatch.setattr(sandbox_runtime_module, "_use_supabase_storage", lambda _db_path=None: True)
    monkeypatch.setattr(sandbox_runtime_module, "_make_sandbox_runtime_repo", lambda _db_path=None: fake_sandbox_runtime_repo)
    monkeypatch.setattr(sandbox_runtime_module, "_make_sandbox_repo", lambda: fake_sandbox_repo)
    monkeypatch.setattr(sandbox_runtime_module, "_make_provider_event_repo", lambda: _FakeEventRepo())

    sandbox_runtime = SQLiteSandboxRuntimeHandle(
        sandbox_runtime_id="runtime-1",
        provider_name="local",
        db_path=Path("/tmp/fake-sandbox.db"),
        observed_state="detached",
        status="active",
    )

    instance = sandbox_runtime.ensure_active_instance(_FakeProvider())

    assert instance.instance_id == "inst-created"
    assert fake_sandbox_repo.binding_updates == [
        {
            "sandbox_id": f"sandbox-{uuid.uuid5(uuid.NAMESPACE_URL, 'mycel-runtime:runtime-1').hex}",
            "provider_env_id": "inst-created",
            "updated_at": "2026-04-17T00:00:05+00:00",
        }
    ]


def test_destroy_instance_records_provider_event_with_schema_runtime_handle(monkeypatch) -> None:
    fake_sandbox_runtime_repo = _FakeDestroySandboxRuntimeRepo()
    fake_event_repo = _StrictEventRepo()
    provider = _FakeDestroyProvider()

    monkeypatch.setattr(sandbox_runtime_module, "_use_supabase_storage", lambda _db_path=None: True)
    monkeypatch.setattr(sandbox_runtime_module, "_make_sandbox_runtime_repo", lambda _db_path=None: fake_sandbox_runtime_repo)
    monkeypatch.setattr(sandbox_runtime_module, "_make_provider_event_repo", lambda: fake_event_repo)

    sandbox_runtime = SQLiteSandboxRuntimeHandle(
        sandbox_runtime_id="runtime-1",
        provider_name="local",
        current_instance=SandboxInstance(
            instance_id="inst-1",
            provider_name="local",
            status="running",
            created_at=sandbox_runtime_module.utc_now(),
        ),
        db_path=Path("/tmp/fake-sandbox.db"),
        observed_state="running",
        status="active",
    )

    sandbox_runtime.destroy_instance(provider, source="test")

    assert provider.destroyed == ["inst-1"]
    assert fake_event_repo.calls == [
        {
            "provider_name": "local",
            "instance_id": "inst-1",
            "event_type": "intent.destroy",
            "payload": {"instance_id": "inst-1", "source": "test"},
            "matched_runtime_handle": "runtime-1",
            "matched_sandbox_id": f"sandbox-{uuid.uuid5(uuid.NAMESPACE_URL, 'mycel-runtime:runtime-1').hex}",
        }
    ]
