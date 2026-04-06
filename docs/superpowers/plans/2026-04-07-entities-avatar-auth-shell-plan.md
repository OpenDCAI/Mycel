# Entities Avatar Auth Shell Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make avatar upload/delete ownership checks a single router-owned shell while preserving existing 404, 403, and avatar file behavior.

**Architecture:** Keep authorization semantics in `backend/web/routers/entities.py`, extract only the repeated avatar target lookup/owner gate, and prove unchanged behavior with focused route tests. This is a router seam, not an avatar-processing or auth-service rewrite.

**Tech Stack:** FastAPI, pytest, plain router helpers

---

### Task 1: Write focused avatar auth regressions

**Files:**
- Create: `tests/Fix/test_entities_avatar_auth_shell.py`
- Read: `backend/web/routers/entities.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_avatar_member_helper_allows_self_or_owner():
    ...


def test_avatar_member_helper_raises_404_for_missing_member():
    ...


def test_avatar_member_helper_raises_403_for_unrelated_user():
    ...


@pytest.mark.asyncio
async def test_delete_avatar_route_uses_auth_shell():
    ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/Fix/test_entities_avatar_auth_shell.py -q`
Expected: FAIL because the router-local avatar auth helper does not exist yet.

- [ ] **Step 3: Commit the red test**

```bash
git add tests/Fix/test_entities_avatar_auth_shell.py
git commit -m "test: cover entities avatar auth shell"
```

### Task 2: Collapse repeated avatar ownership checks into one router helper

**Files:**
- Modify: `backend/web/routers/entities.py`
- Modify: `tests/Fix/test_entities_avatar_auth_shell.py`

- [ ] **Step 1: Add the minimal router helper**

```python
def _get_owned_avatar_member_or_404(member_id: str, current_user_id: str, member_repo: Any):
    member = member_repo.get_by_id(member_id)
    if not member:
        raise HTTPException(404, "Member not found")
    if member_id == current_user_id or member.owner_user_id == current_user_id:
        return member
    raise HTTPException(403, "Not authorized")
```

- [ ] **Step 2: Replace repeated upload/delete auth shell with the helper**

```python
member = _get_owned_avatar_member_or_404(member_id, current_user_id, repo)
```

- [ ] **Step 3: Keep avatar-specific route logic untouched**

```python
ct = file.content_type or ""
...
avatar_path = process_and_save_avatar(data, member_id)
```

- [ ] **Step 4: Run focused tests to verify green**

Run: `uv run pytest tests/Fix/test_entities_avatar_auth_shell.py -q`
Expected: PASS

- [ ] **Step 5: Commit the router auth-shell alignment**

```bash
git add backend/web/routers/entities.py tests/Fix/test_entities_avatar_auth_shell.py
git commit -m "fix: align entities avatar auth shell"
```

### Task 3: Final verification and PR prep

**Files:**
- Modify: `docs/superpowers/specs/2026-04-07-entities-avatar-auth-shell-design.md`
- Modify: `docs/superpowers/plans/2026-04-07-entities-avatar-auth-shell-plan.md`

- [ ] **Step 1: Run branch proof**

Run: `uv run pytest tests/Fix/test_entities_avatar_auth_shell.py tests/Fix/test_panel_auth_shell_coherence.py tests/Fix/test_panel_task_owner_contract.py tests/Fix/test_thread_launch_config_contract.py -q`
Expected: PASS

Run: `python3 -m py_compile backend/web/routers/entities.py tests/Fix/test_entities_avatar_auth_shell.py`
Expected: exit 0

- [ ] **Step 2: Update docs if implementation exposed a narrower stopline**

Keep the stopline explicit:

- avatar auth shell only
- no avatar processing rewrite
- no entity/profile/thread spillover

- [ ] **Step 3: Commit docs and verification-ready state**

```bash
git add docs/superpowers/specs/2026-04-07-entities-avatar-auth-shell-design.md docs/superpowers/plans/2026-04-07-entities-avatar-auth-shell-plan.md
git commit -m "docs: capture entities avatar auth shell seam"
```
