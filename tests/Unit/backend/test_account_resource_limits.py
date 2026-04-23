from __future__ import annotations

from types import SimpleNamespace

from backend.sandboxes import account as account_service


def test_list_account_resource_limits_reads_thread_repo_from_threads_runtime_state(monkeypatch):
    thread_repo = object()
    settings_repo = SimpleNamespace(get_account_resource_limits=lambda _user_id: None)
    app = SimpleNamespace(
        state=SimpleNamespace(
            threads_runtime_state=SimpleNamespace(thread_repo=thread_repo),
            runtime_storage_state=SimpleNamespace(
                supabase_client=object(),
                storage_container=SimpleNamespace(user_settings_repo=lambda: settings_repo),
            ),
        )
    )

    captured: dict[str, object] = {}

    monkeypatch.setattr(
        account_service.sandbox_service,
        "count_user_visible_sandboxes_by_provider",
        lambda user_id, **kwargs: captured.update({"user_id": user_id, **kwargs}) or {"local": 1},
    )

    result = account_service.list_account_resource_limits(app, "owner-1")

    assert result["items"][0]["provider_name"] == "local"
    assert result["items"][0]["used"] == 1
    assert captured["user_id"] == "owner-1"
    assert captured["thread_repo"] is thread_repo
