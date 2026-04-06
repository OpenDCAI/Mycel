# Invite Codes Router Shell Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deduplicate the invite-codes router's repeated repo-call and error-mapping shell while preserving each route's Chinese `500` prefix and revoke's `404` contract.

**Architecture:** Keep the change inside `backend/web/routers/invite_codes.py`. Introduce one router-local helper that gets the repo, runs the named repo method in `asyncio.to_thread`, preserves `HTTPException`, and maps generic errors with a route-provided prefix.

**Tech Stack:** FastAPI, pytest, Python 3.12

---

### Task 1: Lock The Router Shell With Failing Tests

**Files:**
- Create: `tests/Integration/test_invite_codes_router.py`
- Reference: `backend/web/routers/invite_codes.py`

- [ ] **Step 1: Add focused tests for the helper and route delegation**

Add tests that cover:

```python
@pytest.mark.asyncio
async def test_call_invite_code_repo_returns_repo_result() -> None:
    ...


@pytest.mark.asyncio
async def test_call_invite_code_repo_maps_exception_to_prefixed_500() -> None:
    ...


@pytest.mark.asyncio
async def test_call_invite_code_repo_preserves_http_exception() -> None:
    ...


@pytest.mark.asyncio
async def test_list_invite_codes_uses_router_helper(monkeypatch: pytest.MonkeyPatch) -> None:
    ...


@pytest.mark.asyncio
async def test_revoke_invite_code_uses_helper_and_keeps_404(monkeypatch: pytest.MonkeyPatch) -> None:
    ...
```

- [ ] **Step 2: Run the focused invite-codes router test file and verify RED**

Run: `uv run pytest tests/Integration/test_invite_codes_router.py -q`

Expected: FAIL because the new helper contract does not exist yet.

### Task 2: Implement The Minimal Router-Local Helper

**Files:**
- Modify: `backend/web/routers/invite_codes.py`
- Test: `tests/Integration/test_invite_codes_router.py`

- [ ] **Step 1: Add the minimal helper**

Add:

```python
async def _call_invite_code_repo(
    request: Request,
    error_prefix: str,
    method_name: str,
    *args: Any,
    **kwargs: Any,
) -> Any:
    ...
```

- [ ] **Step 2: Replace only the duplicated shell**

Update only:

```python
list_invite_codes(...)
generate_invite_code(...)
revoke_invite_code(...)
validate_invite_code(...)
```

Keep each route's Chinese `500` prefix explicit at the callsite, and keep revoke's `404` branch in the route.

- [ ] **Step 3: Run the focused invite-codes router test file and verify GREEN**

Run: `uv run pytest tests/Integration/test_invite_codes_router.py -q`

Expected: PASS

### Task 3: Run Regression Verification

**Files:**
- Verify only

- [ ] **Step 1: Run the focused regression set**

Run: `uv run pytest tests/Integration/test_invite_codes_router.py tests/Integration/test_auth_router.py tests/Integration/test_messaging_router.py -q`

Expected: PASS

- [ ] **Step 2: Run syntax verification**

Run: `python3 -m py_compile backend/web/routers/invite_codes.py tests/Integration/test_invite_codes_router.py`

Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add backend/web/routers/invite_codes.py tests/Integration/test_invite_codes_router.py docs/superpowers/specs/2026-04-07-invite-codes-router-shell-design.md docs/superpowers/plans/2026-04-07-invite-codes-router-shell-plan.md
git commit -m "fix: align invite codes router shell"
```
