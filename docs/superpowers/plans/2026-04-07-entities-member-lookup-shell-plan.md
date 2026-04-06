# Entities Member Lookup Shell Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deduplicate the repeated public member lookup shell in `entities.py` while preserving the route-specific behavior after the lookup.

**Architecture:** Keep the change inside `backend/web/routers/entities.py`. Introduce one router-local helper that returns the member or raises `404 "Member not found"`, then reuse it from `get_entity_profile` and `get_agent_thread` without touching profile shaping or thread lookup semantics.

**Tech Stack:** FastAPI, pytest, Python 3.12

---

### Task 1: Lock The Lookup Contract With Failing Tests

**Files:**
- Modify: `tests/Integration/test_entities_router.py`
- Reference: `backend/web/routers/entities.py`

- [ ] **Step 1: Add focused tests for the lookup helper**

Add tests that cover:

```python
def test_get_member_or_404_returns_member() -> None:
    ...


def test_get_member_or_404_raises_for_missing_member() -> None:
    ...


@pytest.mark.asyncio
async def test_get_entity_profile_uses_member_lookup_helper(monkeypatch: pytest.MonkeyPatch) -> None:
    ...


@pytest.mark.asyncio
async def test_get_agent_thread_uses_member_lookup_helper(monkeypatch: pytest.MonkeyPatch) -> None:
    ...
```

- [ ] **Step 2: Run the focused entities router test file and verify RED**

Run: `uv run pytest tests/Integration/test_entities_router.py -q`

Expected: FAIL because the new helper contract does not exist yet.

### Task 2: Implement The Minimal Router-Local Helper

**Files:**
- Modify: `backend/web/routers/entities.py`
- Test: `tests/Integration/test_entities_router.py`

- [ ] **Step 1: Add the minimal helper**

Add a helper with this shape:

```python
def _get_member_or_404(app: Any, user_id: str) -> Any:
    ...
```

- [ ] **Step 2: Replace the repeated route-local lookup**

Update only:

```python
get_entity_profile(...)
get_agent_thread(...)
```

Do not touch any later route-specific branches.

- [ ] **Step 3: Run the focused entities router test file and verify GREEN**

Run: `uv run pytest tests/Integration/test_entities_router.py -q`

Expected: PASS

### Task 3: Run Regression Verification

**Files:**
- Verify only

- [ ] **Step 1: Run the focused regression set**

Run: `uv run pytest tests/Integration/test_entities_router.py tests/Fix/test_entities_avatar_auth_shell.py -q`

Expected: PASS

- [ ] **Step 2: Run syntax verification**

Run: `python3 -m py_compile backend/web/routers/entities.py tests/Integration/test_entities_router.py`

Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add backend/web/routers/entities.py tests/Integration/test_entities_router.py docs/superpowers/specs/2026-04-07-entities-member-lookup-shell-design.md docs/superpowers/plans/2026-04-07-entities-member-lookup-shell-plan.md
git commit -m "fix: align entities member lookup shell"
```
