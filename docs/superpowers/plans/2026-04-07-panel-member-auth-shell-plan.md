# Panel Member Auth Shell Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make panel member ownership checks a single router-owned shell while preserving existing 404, 403, and builtin guard behavior.

**Architecture:** Keep auth semantics in `backend/web/routers/panel.py`, extract only the repeated member lookup/owner gate, and prove unchanged behavior with focused route tests. This is a router seam, not a service or storage rewrite.

**Tech Stack:** FastAPI, pytest, plain router helpers

---

### Task 1: Write focused panel member auth regressions

**Files:**
- Modify: `tests/Fix/test_panel_auth_shell_coherence.py`
- Read: `backend/web/routers/panel.py`

- [ ] **Step 1: Write the failing tests**

```python
@pytest.mark.asyncio
async def test_get_member_route_rejects_wrong_owner():
    ...


@pytest.mark.asyncio
async def test_update_member_route_returns_404_for_missing_member():
    ...


@pytest.mark.asyncio
async def test_delete_member_route_keeps_builtin_guard_before_owner_lookup():
    ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/Fix/test_panel_auth_shell_coherence.py -q`
Expected: FAIL because the helper-backed member shell does not exist yet, so the new focused expectations are not anchored.

- [ ] **Step 3: Commit the red test**

```bash
git add tests/Fix/test_panel_auth_shell_coherence.py
git commit -m "test: cover panel member auth shell"
```

### Task 2: Collapse repeated member ownership checks into one router helper

**Files:**
- Modify: `backend/web/routers/panel.py`
- Modify: `tests/Fix/test_panel_auth_shell_coherence.py`

- [ ] **Step 1: Add the minimal router helper**

```python
def _get_owned_member_or_404(member_id: str, user_id: str) -> dict[str, Any]:
    item = member_service.get_member(member_id)
    if not item:
        raise HTTPException(404, "Member not found")
    if item.get("owner_user_id") != user_id:
        raise HTTPException(403, "Forbidden")
    return item
```

- [ ] **Step 2: Replace repeated member lookup / owner checks in member routes**

```python
existing = await asyncio.to_thread(_get_owned_member_or_404, member_id, user_id)
```

- [ ] **Step 3: Keep builtin route guards explicit**

```python
if member_id == "__leon__":
    raise HTTPException(403, "Cannot publish builtin member")
```

- [ ] **Step 4: Run focused tests to verify green**

Run: `uv run pytest tests/Fix/test_panel_auth_shell_coherence.py -q`
Expected: PASS

- [ ] **Step 5: Commit the router auth-shell alignment**

```bash
git add backend/web/routers/panel.py tests/Fix/test_panel_auth_shell_coherence.py
git commit -m "fix: align panel member auth shell"
```

### Task 3: Final verification and PR prep

**Files:**
- Modify: `docs/superpowers/specs/2026-04-07-panel-member-auth-shell-design.md`
- Modify: `docs/superpowers/plans/2026-04-07-panel-member-auth-shell-plan.md`

- [ ] **Step 1: Run branch proof**

Run: `uv run pytest tests/Fix/test_panel_auth_shell_coherence.py tests/Fix/test_panel_task_owner_contract.py -q`
Expected: PASS

Run: `python3 -m py_compile backend/web/routers/panel.py tests/Fix/test_panel_auth_shell_coherence.py`
Expected: exit 0

- [ ] **Step 2: Update docs if implementation exposed a narrower stopline**

Keep the stopline explicit:

- panel member auth shell only
- no member service rewrite
- no task / cron / monitor spillover

- [ ] **Step 3: Commit docs and verification-ready state**

```bash
git add docs/superpowers/specs/2026-04-07-panel-member-auth-shell-design.md docs/superpowers/plans/2026-04-07-panel-member-auth-shell-plan.md
git commit -m "docs: capture panel member auth shell seam"
```
