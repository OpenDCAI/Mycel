# Threads Member Ownership Shell Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deduplicate the router-local member lookup and ownership shell in `threads.py` for `resolve_main_thread` and `GET/POST /default-config` without changing route semantics.

**Architecture:** Keep the change inside `backend/web/routers/threads.py`. Introduce one soft lookup helper and one strict wrapper helper so `/main` can keep returning `{"thread": None}` while `/default-config` keeps returning `403 "Not authorized"`.

**Tech Stack:** FastAPI, pytest, Python 3.12

---

### Task 1: Lock The Contract With Failing Tests

**Files:**
- Modify: `tests/Fix/test_thread_launch_config_contract.py`
- Reference: `backend/web/routers/threads.py`

- [ ] **Step 1: Add focused tests for the ownership shell**

Add tests that cover:

```python
def test_find_owned_member_returns_none_for_foreign_member() -> None:
    ...

def test_require_owned_member_raises_for_foreign_member() -> None:
    ...

@pytest.mark.asyncio
async def test_resolve_main_thread_returns_null_when_member_is_not_owned() -> None:
    ...

@pytest.mark.asyncio
async def test_get_default_thread_config_raises_when_member_is_not_owned() -> None:
    ...

@pytest.mark.asyncio
async def test_save_default_thread_config_raises_when_member_is_not_owned() -> None:
    ...
```

- [ ] **Step 2: Run the focused test file and verify RED**

Run: `uv run pytest tests/Fix/test_thread_launch_config_contract.py -q`

Expected: FAIL because the new helper contract does not exist yet.

### Task 2: Implement The Minimal Router-Local Helpers

**Files:**
- Modify: `backend/web/routers/threads.py`
- Test: `tests/Fix/test_thread_launch_config_contract.py`

- [ ] **Step 1: Add the minimal helpers**

Add a soft helper and a strict wrapper in `threads.py`:

```python
def _find_owned_member(app: Any, member_id: str, owner_user_id: str) -> Any | None:
    ...


def _require_owned_member(app: Any, member_id: str, owner_user_id: str) -> Any:
    ...
```

- [ ] **Step 2: Replace the repeated route-local lookup/check**

Update only:

```python
resolve_main_thread(...)
get_default_thread_config(...)
save_default_thread_config(...)
```

Do not change `create_thread(...)` or any other route.

- [ ] **Step 3: Run the focused test file and verify GREEN**

Run: `uv run pytest tests/Fix/test_thread_launch_config_contract.py -q`

Expected: PASS

### Task 3: Run Regression Verification

**Files:**
- Verify only

- [ ] **Step 1: Run the focused regression set**

Run: `uv run pytest tests/Fix/test_thread_launch_config_contract.py tests/Integration/test_threads_router.py -q`

Expected: PASS

- [ ] **Step 2: Run syntax verification**

Run: `python3 -m py_compile backend/web/routers/threads.py tests/Fix/test_thread_launch_config_contract.py`

Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add backend/web/routers/threads.py tests/Fix/test_thread_launch_config_contract.py docs/superpowers/specs/2026-04-07-threads-member-ownership-shell-design.md docs/superpowers/plans/2026-04-07-threads-member-ownership-shell-plan.md
git commit -m "fix: align threads member ownership shell"
```
