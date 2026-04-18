from __future__ import annotations

import pytest

from backend.web.routers import webhooks


@pytest.mark.asyncio
async def test_ingest_provider_webhook_keeps_unmatched_payload_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    class _LeaseRepo:
        db_path = "/tmp/fake-sandbox.db"

        def find_by_instance(self, *, provider_name: str, instance_id: str):
            assert provider_name == "local"
            assert instance_id == "inst-1"
            return None

        def close(self) -> None:
            return None

    class _EventRepo:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        def record(self, **kwargs):
            self.calls.append(kwargs)

        def close(self) -> None:
            return None

    class _Container:
        def __init__(self, event_repo: _EventRepo) -> None:
            self._event_repo = event_repo

        def provider_event_repo(self) -> _EventRepo:
            return self._event_repo

    event_repo = _EventRepo()
    monkeypatch.setattr(webhooks, "make_lease_repo", lambda: _LeaseRepo())
    monkeypatch.setattr(webhooks, "_get_container", lambda: _Container(event_repo))

    payload = await webhooks.ingest_provider_webhook(
        "local",
        {"instance_id": "inst-1", "event": "provider.updated"},
    )

    assert payload == {
        "ok": True,
        "provider": "local",
        "instance_id": "inst-1",
        "event_type": "provider.updated",
        "matched": False,
    }
    assert event_repo.calls == [
        {
            "provider_name": "local",
            "instance_id": "inst-1",
            "event_type": "provider.updated",
            "payload": {"instance_id": "inst-1", "event": "provider.updated"},
            "matched_lease_id": None,
            "matched_sandbox_id": None,
        }
    ]


@pytest.mark.asyncio
async def test_ingest_provider_webhook_uses_control_plane_db_path_for_matched_lease(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    class _LeaseRepo:
        def find_by_instance(self, *, provider_name: str, instance_id: str):
            assert provider_name == "local"
            assert instance_id == "inst-2"
            return {"lease_id": "lease-1", "sandbox_id": "sandbox-1"}

        def close(self) -> None:
            return None

    class _EventRepo:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        def record(self, **kwargs):
            self.calls.append(kwargs)

        def close(self) -> None:
            return None

    class _Container:
        def __init__(self, event_repo: _EventRepo) -> None:
            self._event_repo = event_repo

        def provider_event_repo(self) -> _EventRepo:
            return self._event_repo

    class _Lease:
        lease_id = "lease-1"

        def __init__(self) -> None:
            self.applied: list[dict[str, object]] = []

        def apply(self, provider, *, event_type: str, source: str, payload: dict[str, object]) -> None:
            self.applied.append(
                {
                    "provider": provider,
                    "event_type": event_type,
                    "source": source,
                    "payload": payload,
                }
            )

    class _Manager:
        def __init__(self) -> None:
            self.provider = object()

    expected_db_path = tmp_path / "sandbox.db"
    event_repo = _EventRepo()
    lease = _Lease()

    monkeypatch.setattr(webhooks, "resolve_sandbox_db_path", lambda: expected_db_path, raising=False)
    monkeypatch.setattr(webhooks, "make_lease_repo", lambda: _LeaseRepo())
    monkeypatch.setattr(webhooks, "_get_container", lambda: _Container(event_repo))
    monkeypatch.setattr(webhooks, "init_providers_and_managers", lambda: ({}, {"local": _Manager()}))

    def _fake_lease_from_row(row, db_path):
        assert row == {"lease_id": "lease-1", "sandbox_id": "sandbox-1"}
        assert db_path == expected_db_path
        return lease

    monkeypatch.setattr(webhooks, "lease_from_row", _fake_lease_from_row)

    payload = await webhooks.ingest_provider_webhook(
        "local",
        {"instance_id": "inst-2", "event": "provider.running"},
    )

    assert payload["matched"] is True
    assert "lease_id" not in payload
    assert event_repo.calls == [
        {
            "provider_name": "local",
            "instance_id": "inst-2",
            "event_type": "provider.running",
            "payload": {"instance_id": "inst-2", "event": "provider.running"},
            "matched_lease_id": "lease-1",
            "matched_sandbox_id": "sandbox-1",
        }
    ]
    assert lease.applied == [
        {
            "provider": lease.applied[0]["provider"],
            "event_type": "observe.status",
            "source": "webhook",
            "payload": {"status": "running", "raw_event_type": "provider.running"},
        }
    ]


@pytest.mark.asyncio
async def test_list_provider_events_strips_lower_lease_match_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    class _EventRepo:
        def list_recent(self, limit: int):
            assert limit == 25
            return [
                {
                    "event_id": 1,
                    "provider_name": "daytona",
                    "instance_id": "instance-1",
                    "event_type": "started",
                    "matched_lease_id": "lease-1",
                    "matched_sandbox_id": "sandbox-1",
                    "payload": {"ok": True},
                }
            ]

        def close(self) -> None:
            return None

    class _Container:
        def provider_event_repo(self) -> _EventRepo:
            return _EventRepo()

    monkeypatch.setattr(webhooks, "_get_container", lambda: _Container())

    payload = await webhooks.list_provider_events(limit=25)

    assert payload == {
        "items": [
            {
                "event_id": 1,
                "provider_name": "daytona",
                "instance_id": "instance-1",
                "event_type": "started",
                "matched_sandbox_id": "sandbox-1",
                "payload": {"ok": True},
            }
        ],
        "count": 1,
    }
