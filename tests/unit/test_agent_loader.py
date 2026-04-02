from pathlib import Path

from config.loader import AgentLoader


def test_project_agent_file_does_not_claim_bundle_source_dir(tmp_path: Path):
    agents_dir = tmp_path / ".leon" / "agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "explore.md").write_text(
        "---\nname: explore\nmodel: project-model\n---\nproject prompt\n",
        encoding="utf-8",
    )

    agent = AgentLoader(workspace_root=tmp_path).load_all_agents()["explore"]

    assert agent.model == "project-model"
    assert agent.source_dir is None


def test_member_agent_retains_bundle_source_dir(tmp_path: Path, monkeypatch):
    home_root = tmp_path
    monkeypatch.setattr("config.loader.user_home_read_candidates", lambda *parts: (home_root.joinpath(*parts),))
    member_dir = home_root / "members" / "alice"
    member_dir.mkdir(parents=True)
    (member_dir / "agent.md").write_text(
        "---\nname: alice\ntools:\n  - \"*\"\n---\nmember prompt\n",
        encoding="utf-8",
    )

    agent = AgentLoader(workspace_root=tmp_path).load_all_agents()["alice"]

    assert agent.source_dir == member_dir.resolve()
