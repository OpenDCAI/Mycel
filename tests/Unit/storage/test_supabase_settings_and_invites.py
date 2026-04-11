import json

import pytest

from storage.providers.supabase.invite_code_repo import SupabaseInviteCodeRepo
from storage.providers.supabase.user_settings_repo import SupabaseUserSettingsRepo
from tests.fakes.supabase import FakeSupabaseClient


def test_user_settings_recent_workspace_parser_does_not_hide_unexpected_json_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    tables = {
        "user_settings": [
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


def test_invite_code_expiry_does_not_hide_non_string_expires_at() -> None:
    repo = SupabaseInviteCodeRepo(
        FakeSupabaseClient(
            tables={
                "invite_codes": [
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
