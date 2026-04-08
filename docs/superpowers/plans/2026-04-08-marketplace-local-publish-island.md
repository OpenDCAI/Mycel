# Marketplace Local Publish Island Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the normal web marketplace publish path repo-rooted only, without silently sharing the old local member-bundle discovery shell.

**Architecture:** `backend/web/routers/marketplace.py` already proves the web path always has `user_repo + agent_config_repo`. The cleanup is to make `backend/web/services/marketplace_client.py::publish()` treat that repo-backed path as canonical, and push any legacy local-bundle behavior behind an explicit helper instead of leaving it as a shared fallback branch.

**Tech Stack:** Python, pytest, ruff

---

### Task 1: Isolate Repo-Rooted Publish From Local Bundle Publish

**Files:**
- Modify: `backend/web/services/marketplace_client.py`
- Modify: `tests/Unit/platform/test_marketplace_client.py`
- Test: `tests/Integration/test_marketplace_router_user_shell.py`

- [ ] **Step 1: Write the failing unit test for legacy-dir-present publish**

Add this test to `tests/Unit/platform/test_marketplace_client.py` after `test_publish_uses_repo_bundle_when_member_dir_is_absent`:

```python
def test_publish_ignores_legacy_member_dir_when_repos_are_present(tmp_path, monkeypatch):
    import backend.web.services.marketplace_client as marketplace_client

    saved: dict[str, object] = {}
    captured: dict[str, object] = {}
    members_root = tmp_path / "members"
    member_dir = members_root / "agent-user-1"
    member_dir.mkdir(parents=True)
    (member_dir / "agent.md").write_text("---\nname: Legacy Agent\n---\n\nlegacy prompt\n", encoding="utf-8")
    (member_dir / "meta.json").write_text(json.dumps({"version": "9.9.9", "source": {"marketplace_item_id": "legacy-item"}}), encoding="utf-8")

    monkeypatch.setattr(marketplace_client, "members_dir", lambda: members_root)

    user_repo = SimpleNamespace(get_by_id=lambda user_id: SimpleNamespace(id=user_id, agent_config_id="cfg-1"))

    class _AgentConfigRepo:
        def get_config(self, agent_config_id: str):
            return {
                "id": "cfg-1",
                "agent_user_id": "agent-user-1",
                "name": "Repo Agent",
                "description": "from repo",
                "tools": ["search"],
                "system_prompt": "be helpful",
                "status": "draft",
                "version": "0.1.0",
                "created_at": 1,
                "updated_at": 2,
                "meta": {"source": {"marketplace_item_id": "item-parent", "installed_version": "0.1.0"}},
                "runtime": {"tools:search": {"enabled": True, "desc": "Search"}},
                "mcp": {"demo": {"transport": "stdio", "command": "demo"}},
            }

        def list_rules(self, agent_config_id: str):
            return [{"filename": "default.md", "content": "Rule content"}]

        def list_sub_agents(self, agent_config_id: str):
            return [{"name": "Scout", "description": "helper", "tools": ["search"], "system_prompt": "look around"}]

        def list_skills(self, agent_config_id: str):
            return [{"name": "Search", "content": "skill content", "meta_json": {"name": "Search"}}]

        def save_config(self, agent_config_id: str, data: dict):
            saved["agent_config_id"] = agent_config_id
            saved["data"] = data

    monkeypatch.setattr(
        marketplace_client,
        "_hub_api",
        lambda method, path, **kwargs: captured.update({"method": method, "path": path, "json": kwargs["json"]}) or {"item_id": "item-123"},
    )

    result = marketplace_client.publish(
        user_id="agent-user-1",
        type_="member",
        bump_type="patch",
        release_notes="repo publish",
        tags=["repo"],
        visibility="private",
        publisher_user_id="owner-1",
        publisher_username="owner-name",
        user_repo=user_repo,
        agent_config_repo=_AgentConfigRepo(),
    )

    assert result == {"item_id": "item-123"}
    payload = captured["json"]
    assert payload["name"] == "Repo Agent"
    assert payload["version"] == "0.1.1"
    assert payload["parent_item_id"] == "item-parent"
    assert payload["parent_version"] == "0.1.0"
    assert payload["snapshot"]["agent_md"].startswith("---\nname: Repo Agent")
    assert payload["snapshot"]["meta"]["version"] == "0.1.0"
    assert payload["snapshot"]["meta"]["source"] == {"marketplace_item_id": "item-parent", "installed_version": "0.1.0"}
    assert saved["data"]["version"] == "0.1.1"
```

- [ ] **Step 2: Run the unit tests to verify the new test fails**

Run:

```bash
ALL_PROXY= HTTPS_PROXY= HTTP_PROXY= all_proxy= https_proxy= http_proxy= uv run pytest tests/Unit/platform/test_marketplace_client.py -q
```

Expected:
- the new test fails because `publish()` still merges local `meta.json` / member-dir shell into the repo-backed path

- [ ] **Step 3: Implement the minimal repo-rooted publish split**

Update `backend/web/services/marketplace_client.py` with a minimal split:

```python
def _load_local_publish_material(user_id: str) -> tuple[AgentBundle, dict[str, Any], dict[str, Any]]:
    member_dir = members_dir() / user_id
    meta = _read_json(member_dir / "meta.json")
    snapshot = _serialize_user_snapshot(user_id)
    bundle = AgentLoader().load_bundle(member_dir)
    return bundle, meta, snapshot
```

Then reshape `publish()` so the repo-backed path does not merge local member-dir data:

```python
if user_repo is not None and agent_config_repo is not None:
    bundle, meta = _load_repo_publish_material(user_id, user_repo, agent_config_repo)
    snapshot = _bundle_snapshot(bundle)
    snapshot["meta"] = copy.deepcopy(meta)
else:
    bundle, meta, snapshot = _load_local_publish_material(user_id)
```

Keep:
- version bump logic
- `meta["source"]` lineage update after publish
- `save_config(...)` shape

Do not change:
- `download()`
- `upgrade()`
- outward payloads

- [ ] **Step 4: Run focused verification**

Run:

```bash
ALL_PROXY= HTTPS_PROXY= HTTP_PROXY= all_proxy= https_proxy= http_proxy= uv run pytest tests/Unit/platform/test_marketplace_client.py tests/Integration/test_marketplace_router_user_shell.py -q
python3 -m py_compile backend/web/services/marketplace_client.py tests/Unit/platform/test_marketplace_client.py
uv run ruff check backend/web/services/marketplace_client.py tests/Unit/platform/test_marketplace_client.py
```

Expected:
- the marketplace unit suite passes
- marketplace router integration stays green
- `py_compile` passes
- `ruff check` passes

- [ ] **Step 5: Commit the bounded slice**

```bash
git add backend/web/services/marketplace_client.py tests/Unit/platform/test_marketplace_client.py
git commit -m "refactor: isolate repo-backed marketplace publish"
```
