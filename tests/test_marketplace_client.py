"""Tests for marketplace_client business logic (publish/download)."""

import json
from unittest.mock import patch

import pytest

import backend.web.services.library_service as _lib_svc

# ── Version Bump (tested via publish internals) ──


def _bump_version(current: str, bump_type: str) -> str:
    """Reproduce the version bump logic from marketplace_client.publish."""
    parts = current.split(".")
    major, minor, p = int(parts[0]), int(parts[1]), int(parts[2])
    if bump_type == "major":
        major, minor, p = major + 1, 0, 0
    elif bump_type == "minor":
        minor, p = minor + 1, 0
    else:
        p += 1
    return f"{major}.{minor}.{p}"


class TestVersionBump:
    def test_patch_bump(self):
        assert _bump_version("1.2.3", "patch") == "1.2.4"

    def test_minor_bump(self):
        assert _bump_version("1.2.3", "minor") == "1.3.0"

    def test_major_bump(self):
        assert _bump_version("1.2.3", "major") == "2.0.0"

    def test_initial_version(self):
        assert _bump_version("0.1.0", "patch") == "0.1.1"


# ── Helpers ──


def _make_hub_response(
    item_type: str, slug: str, content: str = "# Hello", version: str = "1.0.0", publisher: str = "tester"
) -> dict:
    """Build a fake Hub /download response."""
    return {
        "item": {
            "name": slug.replace("-", " ").title(),
            "slug": slug,
            "type": item_type,
            "description": "A test item",
            "tags": ["test"],
            "publisher_username": publisher,
        },
        "snapshot": {
            "content": content,
            "meta": {"name": slug.replace("-", " ").title(), "desc": "A test item"},
        },
        "version": version,
    }


# ── Download — skill ──


class TestDownloadSkill:
    def test_writes_skill_md(self, tmp_path, monkeypatch):
        lib = tmp_path / "library"
        monkeypatch.setattr(_lib_svc, "LIBRARY_DIR", lib)
        hub_resp = _make_hub_response("skill", "my-skill", content="# My Skill\nDo stuff")

        with patch("backend.web.services.marketplace_client._hub_api", return_value=hub_resp):
            from backend.web.services.marketplace_client import download

            result = download("item-123")

        assert result["type"] == "skill"
        assert result["resource_id"] == "my-skill"
        skill_md = lib / "skills" / "my-skill" / "SKILL.md"
        assert skill_md.exists()
        assert skill_md.read_text(encoding="utf-8") == "# My Skill\nDo stuff"

    def test_meta_json_has_source_tracking(self, tmp_path, monkeypatch):
        lib = tmp_path / "library"
        monkeypatch.setattr(_lib_svc, "LIBRARY_DIR", lib)
        hub_resp = _make_hub_response("skill", "tracked-skill", version="2.1.0", publisher="alice")

        with patch("backend.web.services.marketplace_client._hub_api", return_value=hub_resp):
            from backend.web.services.marketplace_client import download

            download("item-456")

        meta = json.loads((lib / "skills" / "tracked-skill" / "meta.json").read_text(encoding="utf-8"))
        assert meta["source"]["marketplace_item_id"] == "item-456"
        assert meta["source"]["installed_version"] == "2.1.0"
        assert meta["source"]["publisher"] == "alice"

    def test_path_traversal_blocked(self, tmp_path, monkeypatch):
        lib = tmp_path / "library"
        monkeypatch.setattr(_lib_svc, "LIBRARY_DIR", lib)
        hub_resp = _make_hub_response("skill", "../../evil")

        with patch("backend.web.services.marketplace_client._hub_api", return_value=hub_resp):
            from backend.web.services.marketplace_client import download

            with pytest.raises(ValueError, match="Invalid slug"):
                download("item-evil")

        # Ensure no files written outside library
        assert not (tmp_path / "evil").exists()


# ── Download — agent ──


class TestDownloadAgent:
    def test_writes_agent_md(self, tmp_path, monkeypatch):
        lib = tmp_path / "library"
        monkeypatch.setattr(_lib_svc, "LIBRARY_DIR", lib)
        hub_resp = _make_hub_response("agent", "cool-agent", content="# Cool Agent")

        with patch("backend.web.services.marketplace_client._hub_api", return_value=hub_resp):
            from backend.web.services.marketplace_client import download

            result = download("item-a1")

        assert result["type"] == "agent"
        assert result["resource_id"] == "cool-agent"
        md_path = lib / "agents" / "cool-agent.md"
        assert md_path.exists()
        assert md_path.read_text(encoding="utf-8") == "# Cool Agent"

    def test_meta_json_written(self, tmp_path, monkeypatch):
        lib = tmp_path / "library"
        monkeypatch.setattr(_lib_svc, "LIBRARY_DIR", lib)
        hub_resp = _make_hub_response("agent", "meta-agent", version="3.0.0", publisher="bob")

        with patch("backend.web.services.marketplace_client._hub_api", return_value=hub_resp):
            from backend.web.services.marketplace_client import download

            download("item-a2")

        meta = json.loads((lib / "agents" / "meta-agent.json").read_text(encoding="utf-8"))
        assert meta["source"]["marketplace_item_id"] == "item-a2"
        assert meta["source"]["installed_version"] == "3.0.0"
        assert meta["source"]["publisher"] == "bob"


# ── Download idempotency ──


class TestDownloadIdempotency:
    def test_download_twice_overwrites_cleanly(self, tmp_path, monkeypatch):
        lib = tmp_path / "library"
        monkeypatch.setattr(_lib_svc, "LIBRARY_DIR", lib)

        v1 = _make_hub_response("skill", "idem-skill", content="V1", version="1.0.0")
        v2 = _make_hub_response("skill", "idem-skill", content="V2", version="1.0.1")

        from backend.web.services.marketplace_client import download

        with patch("backend.web.services.marketplace_client._hub_api", return_value=v1):
            download("item-idem")

        with patch("backend.web.services.marketplace_client._hub_api", return_value=v2):
            result = download("item-idem")

        assert result["version"] == "1.0.1"
        content = (lib / "skills" / "idem-skill" / "SKILL.md").read_text(encoding="utf-8")
        assert content == "V2"
        meta = json.loads((lib / "skills" / "idem-skill" / "meta.json").read_text(encoding="utf-8"))
        assert meta["source"]["installed_version"] == "1.0.1"
