import json

import pytest

from storage.providers.supabase.invite_code_repo import SupabaseInviteCodeRepo
from storage.providers.supabase.user_settings_repo import SupabaseUserSettingsRepo
from tests.fakes.supabase import FakeSupabaseClient


class _RecordingSupabaseClient(FakeSupabaseClient):
    def __init__(self, tables: dict):
        super().__init__(tables=tables)
        self.table_names: list[str] = []

    def table(self, table_name: str):
        resolved_table = f"{self._schema_name}.{table_name}" if self._schema_name else table_name
        self.table_names.append(resolved_table)
        return super().table(table_name)

    def schema(self, schema_name: str):
        scoped = _RecordingSupabaseClient(self._tables)
        scoped._schema_name = schema_name
        scoped.table_names = self.table_names
        return scoped


def test_user_settings_recent_workspace_parser_does_not_hide_unexpected_json_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    tables = {
        "identity.user_settings": [
            {
                "user_id": "user-1",
                "recent_workspaces": '["/workspace"]',
            }
        ]
    }
    repo = SupabaseUserSettingsRepo(FakeSupabaseClient(tables=tables))

    def _raise_runtime_error(_value: str) -> list[str]:
        raise RuntimeError("json loader unavailable")

    monkeypatch.setattr(json, "loads", _raise_runtime_error)

    with pytest.raises(RuntimeError, match="json loader unavailable"):
        repo.get("user-1")


def test_user_settings_reads_account_resource_limits() -> None:
    repo = SupabaseUserSettingsRepo(
        FakeSupabaseClient(
            tables={
                "identity.user_settings": [
                    {
                        "user_id": "user-1",
                        "account_resource_limits": {"sandbox": {"daytona_selfhost": 5}},
                    }
                ]
            }
        )
    )

    assert repo.get_account_resource_limits("user-1") == {"sandbox": {"daytona_selfhost": 5}}


def test_user_settings_repo_uses_identity_schema_for_reads_and_writes() -> None:
    tables = {"identity.user_settings": [{"user_id": "user-1", "default_model": "leon:large"}]}
    client = _RecordingSupabaseClient(tables)
    repo = SupabaseUserSettingsRepo(client)

    assert repo.get("user-1")["default_model"] == "leon:large"

    repo.set_default_model("user-1", "leon:small")

    assert client.table_names == ["identity.user_settings", "identity.user_settings"]
    assert tables["identity.user_settings"][0]["default_model"] == "leon:small"
    assert "user_settings" not in tables


def test_invite_code_expiry_does_not_hide_non_string_expires_at() -> None:
    repo = SupabaseInviteCodeRepo(
        FakeSupabaseClient(
            tables={
                "identity.invite_codes": [
                    {
                        "code": "BAD-DATE",
                        "used_by": None,
                        "expires_at": 123,
                    }
                ]
            }
        )
    )

    with pytest.raises(AttributeError):
        repo.is_valid("BAD-DATE")


def test_invite_code_repo_uses_identity_schema_for_reads_and_writes() -> None:
    tables = {"identity.invite_codes": []}
    client = _RecordingSupabaseClient(tables)
    repo = SupabaseInviteCodeRepo(client)

    repo.generate(created_by="user-1", expires_days=None)
    repo.list_all()

    assert client.table_names == [
        "identity.invite_codes",
        "identity.invite_codes",
        "identity.invite_codes",
    ]
    assert tables["identity.invite_codes"][0]["created_by"] == "user-1"
    assert "invite_codes" not in tables


def test_invite_code_use_is_idempotent_for_same_user() -> None:
    tables = {
        "identity.invite_codes": [
            {
                "code": "INVITE-1",
                "used_by": None,
                "used_at": None,
                "expires_at": None,
            }
        ]
    }
    repo = SupabaseInviteCodeRepo(FakeSupabaseClient(tables=tables))

    first = repo.use("INVITE-1", "user-1")
    replay = repo.use("INVITE-1", "user-1")

    assert first is not None
    assert replay is not None
    assert first["used_by"] == "user-1"
    assert replay["used_by"] == "user-1"


def test_invite_code_can_only_be_replayed_by_consumer() -> None:
    repo = SupabaseInviteCodeRepo(
        FakeSupabaseClient(
            tables={
                "identity.invite_codes": [
                    {
                        "code": "INVITE-1",
                        "used_by": "user-1",
                        "used_at": "2026-04-27T00:00:00+00:00",
                        "expires_at": None,
                    }
                ]
            }
        )
    )

    assert repo.is_usable_by("INVITE-1", "user-1") is True
    assert repo.is_usable_by("INVITE-1", "user-2") is False
    assert repo.use("INVITE-1", "user-2") is None
