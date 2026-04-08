# Marketplace Local-Only Publish Fallback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the silent local-only `publish()` fallback so web publish stays repo-rooted and missing repos fail loudly.

**Architecture:** The normal marketplace web route already proves the live contract: `marketplace_client.publish()` is called with `user_repo + agent_config_repo`. The cleanup is to make that requirement explicit in `publish()` and stop silently reading `members_dir` when those repos are absent. This leaves lineage, download, upgrade, and install untouched.

**Tech Stack:** Python, pytest, ruff

---

### Task 1: Fail Loudly When Publish Lacks Repos

**Files:**
- Modify: `backend/web/services/marketplace_client.py`
- Modify: `tests/Unit/platform/test_marketplace_client.py`

- [ ] **Step 1: Write the failing test**

Add this test to `tests/Unit/platform/test_marketplace_client.py`:

```python
def test_publish_requires_repos(monkeypatch):
    import backend.web.services.marketplace_client as marketplace_client

    monkeypatch.setattr(
        marketplace_client,
        "members_dir",
        lambda: (_ for _ in ()).throw(AssertionError("local member dir should not be touched")),
    )

    with pytest.raises(RuntimeError, match="user_repo and agent_config_repo are required"):
        marketplace_client.publish(
            user_id="agent-user-1",
            type_="member",
            bump_type="patch",
            release_notes="repo publish",
            tags=["repo"],
            visibility="private",
            publisher_user_id="owner-1",
            publisher_username="owner-name",
        )
```

- [ ] **Step 2: Run the focused tests to verify red**

Run:

```bash
ALL_PROXY= HTTPS_PROXY= HTTP_PROXY= all_proxy= https_proxy= http_proxy= uv run pytest tests/Unit/platform/test_marketplace_client.py -q
```

Expected:
- the new test fails because `publish()` still touches the local fallback branch instead of failing loudly

- [ ] **Step 3: Write the minimal implementation**

Update `backend/web/services/marketplace_client.py::publish()` so it requires repos:

```python
if user_repo is None or agent_config_repo is None:
    raise RuntimeError("user_repo and agent_config_repo are required to publish member bundles")
bundle, meta = _load_repo_publish_material(user_id, user_repo, agent_config_repo)
snapshot = _bundle_snapshot(bundle)
snapshot["meta"] = copy.deepcopy(meta)
```

Delete the old fallback branch that called:

```python
_serialize_user_snapshot(user_id)
AgentLoader().load_bundle(member_dir)
```

Do not change:
- version bump logic
- lineage/meta update after publish
- `download()`
- `upgrade()`

- [ ] **Step 4: Run focused verification**

Run:

```bash
ALL_PROXY= HTTPS_PROXY= HTTP_PROXY= all_proxy= https_proxy= http_proxy= uv run pytest tests/Unit/platform/test_marketplace_client.py tests/Integration/test_marketplace_router_user_shell.py -q
python3 -m py_compile backend/web/services/marketplace_client.py tests/Unit/platform/test_marketplace_client.py
uv run ruff check backend/web/services/marketplace_client.py tests/Unit/platform/test_marketplace_client.py
```

Expected:
- all tests pass
- `py_compile` passes
- `ruff check` passes

- [ ] **Step 5: Commit the bounded slice**

```bash
git add backend/web/services/marketplace_client.py tests/Unit/platform/test_marketplace_client.py
git commit -m "refactor: remove local marketplace publish fallback"
```
