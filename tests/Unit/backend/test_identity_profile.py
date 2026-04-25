from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.identity import profile


def test_get_profile_requires_user_row(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    local_config = tmp_path / ".leon" / "config.json"
    local_config.parent.mkdir(parents=True)
    local_config.write_text(
        '{"profile": {"name": "host-user", "initials": "HU", "email": "host@example.com"}}',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="user is required"):
        profile.get_profile()


def test_get_profile_uses_user_row() -> None:
    user = SimpleNamespace(display_name="Ada Lovelace", email="ada@example.com")

    assert profile.get_profile(user) == {
        "name": "Ada Lovelace",
        "initials": "AL",
        "email": "ada@example.com",
    }
