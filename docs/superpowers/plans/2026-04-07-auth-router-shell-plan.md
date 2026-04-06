# Auth Router Shell Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deduplicate the auth router's repeated service-call and `ValueError` mapping shell while preserving the distinct `400` vs `401` route contracts.

**Architecture:** Keep the change inside `backend/web/routers/auth.py`. Introduce one helper that receives a route-specific status code and auth service method name, then use it from the four auth routes without altering payloads or auth service behavior.

**Tech Stack:** FastAPI, pytest, Python 3.12

---

### Task 1: Lock The Shell Contract With Failing Tests

**Files:**
- Modify: `tests/Integration/test_auth_router.py`
- Reference: `backend/web/routers/auth.py`

- [ ] **Step 1: Add focused tests for the router helper**

Add tests that cover:

```python
@pytest.mark.asyncio
async def test_call_auth_service_returns_service_result() -> None:
    ...


@pytest.mark.asyncio
async def test_call_auth_service_maps_value_error_to_given_status() -> None:
    ...


@pytest.mark.asyncio
async def test_send_otp_uses_auth_router_helper(monkeypatch: pytest.MonkeyPatch) -> None:
    ...


@pytest.mark.asyncio
async def test_login_uses_auth_router_helper(monkeypatch: pytest.MonkeyPatch) -> None:
    ...
```

- [ ] **Step 2: Run the focused auth router test file and verify RED**

Run: `uv run pytest tests/Integration/test_auth_router.py -q`

Expected: FAIL because the new helper contract does not exist yet.

### Task 2: Implement The Minimal Router-Local Helper

**Files:**
- Modify: `backend/web/routers/auth.py`
- Test: `tests/Integration/test_auth_router.py`

- [ ] **Step 1: Add the minimal helper**

Add an async helper with this shape:

```python
async def _call_auth_service(
    app: Any,
    status_code: int,
    method_name: str,
    *args: Any,
) -> Any:
    ...
```

- [ ] **Step 2: Replace the repeated route-local shell**

Update only:

```python
send_otp(...)
verify_otp(...)
complete_register(...)
login(...)
```

Keep route-specific status codes explicit at each callsite.

- [ ] **Step 3: Run the focused auth router test file and verify GREEN**

Run: `uv run pytest tests/Integration/test_auth_router.py -q`

Expected: PASS

### Task 3: Run Regression Verification

**Files:**
- Verify only

- [ ] **Step 1: Run the focused regression set**

Run: `uv run pytest tests/Integration/test_auth_router.py tests/Fix/test_thread_launch_config_contract.py -q`

Expected: PASS

- [ ] **Step 2: Run syntax verification**

Run: `python3 -m py_compile backend/web/routers/auth.py tests/Integration/test_auth_router.py`

Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add backend/web/routers/auth.py tests/Integration/test_auth_router.py docs/superpowers/specs/2026-04-07-auth-router-shell-design.md docs/superpowers/plans/2026-04-07-auth-router-shell-plan.md
git commit -m "fix: align auth router shell"
```
