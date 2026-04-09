from __future__ import annotations

import inspect

import pytest

from backend.web.routers import webhooks


def test_webhooks_router_no_longer_imports_sqlite_lease_repo() -> None:
    source = inspect.getsource(webhooks)

    assert "storage.providers.sqlite.lease_repo" not in source
    assert "storage.runtime" in source


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
        }
    ]
