# Messaging Chat Access Shell Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deduplicate the repeated chat lookup and membership gate in the messaging router while preserving `404` and `403` behavior for chat detail and delete.

**Architecture:** Keep the change inside `backend/web/routers/messaging.py`. Introduce one router-local helper that loads a chat, enforces membership, and returns the chat object; then use it from `get_chat` and `delete_chat` only.

**Tech Stack:** FastAPI, pytest, Python 3.12

---

### Task 1: Lock The Chat Access Shell With Failing Tests

**Files:**
- Create: `tests/Integration/test_messaging_router.py`
- Reference: `backend/web/routers/messaging.py`

- [ ] **Step 1: Add focused tests for the router helper**

Add tests that cover:

```python
def test_get_accessible_chat_or_404_returns_chat() -> None:
    ...


def test_get_accessible_chat_or_404_raises_404_for_missing_chat() -> None:
    ...


def test_get_accessible_chat_or_404_raises_403_for_non_member() -> None:
    ...


@pytest.mark.asyncio
async def test_get_chat_uses_access_helper(monkeypatch: pytest.MonkeyPatch) -> None:
    ...


@pytest.mark.asyncio
async def test_delete_chat_uses_access_helper(monkeypatch: pytest.MonkeyPatch) -> None:
    ...
```

- [ ] **Step 2: Run the focused messaging router test file and verify RED**

Run: `uv run pytest tests/Integration/test_messaging_router.py -q`

Expected: FAIL because the new helper contract does not exist yet.

### Task 2: Implement The Minimal Router-Local Helper

**Files:**
- Modify: `backend/web/routers/messaging.py`
- Test: `tests/Integration/test_messaging_router.py`

- [ ] **Step 1: Add the minimal helper**

Add:

```python
def _get_accessible_chat_or_404(app: Any, chat_id: str, user_id: str) -> Any:
    ...
```

- [ ] **Step 2: Replace only the duplicated route shell**

Update only:

```python
get_chat(...)
delete_chat(...)
```

Do not change `list_messages(...)`.

- [ ] **Step 3: Run the focused messaging router test file and verify GREEN**

Run: `uv run pytest tests/Integration/test_messaging_router.py -q`

Expected: PASS

### Task 3: Run Regression Verification

**Files:**
- Verify only

- [ ] **Step 1: Run the focused regression set**

Run: `uv run pytest tests/Integration/test_messaging_router.py tests/Integration/test_auth_router.py tests/Integration/test_entities_router.py -q`

Expected: PASS

- [ ] **Step 2: Run syntax verification**

Run: `python3 -m py_compile backend/web/routers/messaging.py tests/Integration/test_messaging_router.py`

Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add backend/web/routers/messaging.py tests/Integration/test_messaging_router.py docs/superpowers/specs/2026-04-07-messaging-chat-access-shell-design.md docs/superpowers/plans/2026-04-07-messaging-chat-access-shell-plan.md
git commit -m "fix: align messaging chat access shell"
```
