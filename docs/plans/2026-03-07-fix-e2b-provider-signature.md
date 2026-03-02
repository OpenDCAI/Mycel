# Fix E2B/AgentBay Provider Signature Mismatch

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix provider signature mismatch that breaks file upload for E2B and AgentBay sandboxes

**Root Cause:** E2B and AgentBay providers' `create_session()` only accept `context_id`, but `sandbox/lease.py:674` calls it with `thread_id` parameter. Docker, Local, and Daytona were updated but E2B/AgentBay were missed.

**Why Tests Didn't Catch This:** Phase 2 tests used mock providers with custom signatures, not real provider classes. They tested sync logic in isolation but didn't verify provider interface compatibility.

**Tech Stack:** Python, provider pattern, integration testing

---

## Task 1: Fix E2B Provider Signature

**Files:**
- Modify: `sandbox/providers/e2b.py:67`

**Step 1: Read current signature**

Current: `def create_session(self, context_id: str | None = None) -> SessionInfo:`

**Step 2: Update to match other providers**

```python
def create_session(self, context_id: str | None = None, thread_id: str | None = None) -> SessionInfo:
```

**Step 3: Verify no usage of thread_id needed**

E2B doesn't use thread_id internally (no bind mounts, no thread-specific config). Parameter is for interface compatibility only.

**Step 4: Commit**

```bash
git add sandbox/providers/e2b.py
git commit -m "fix: add thread_id parameter to E2BProvider.create_session()"
```

---

## Task 2: Fix AgentBay Provider Signature

**Files:**
- Modify: `sandbox/providers/agentbay.py:63`

**Step 1: Update signature**

```python
def create_session(self, context_id: str | None = None, thread_id: str | None = None) -> SessionInfo:
```

**Step 2: Commit**

```bash
git add sandbox/providers/agentbay.py
git commit -m "fix: add thread_id parameter to AgentBayProvider.create_session()"
```

---

## Task 3: Add Provider Signature Validation Test

**Files:**
- Create: `tests/sandbox/test_provider_signatures.py`

**Step 1: Write test that validates all providers have matching signatures**

```python
def test_all_providers_accept_thread_id():
    """Verify all providers accept thread_id in create_session()."""
    import inspect
    from sandbox.providers.docker import DockerProvider
    from sandbox.providers.local import LocalProvider
    from sandbox.providers.daytona import DaytonaProvider
    from sandbox.providers.e2b import E2BProvider
    from sandbox.providers.agentbay import AgentBayProvider

    providers = [DockerProvider, LocalProvider, DaytonaProvider, E2BProvider, AgentBayProvider]

    for provider_class in providers:
        sig = inspect.signature(provider_class.create_session)
        params = sig.parameters

        assert 'context_id' in params, f"{provider_class.__name__} missing context_id"
        assert 'thread_id' in params, f"{provider_class.__name__} missing thread_id"
```

**Step 2: Run test to verify it passes**

Run: `uv run pytest tests/sandbox/test_provider_signatures.py -v`
Expected: PASS

**Step 3: Commit**

```bash
git add tests/sandbox/test_provider_signatures.py
git commit -m "test: add provider signature validation"
```

---

## Task 4: Verify E2E Fix

**Files:**
- Run existing E2E tests

**Step 1: Run E2E tests**

Run: `uv run pytest tests/e2e/test_e2b_sandbox.py -v`
Expected: PASS (file upload now works)

**Step 2: Manual verification**

Start backend, upload file via UI, verify agent can access it in E2B sandbox.

---

## Summary

**What was fixed:**
- E2B and AgentBay providers now accept `thread_id` parameter
- Added signature validation test to prevent future regressions
- File upload/sync now works for all sandbox types

**Lesson learned:**
Mock-based tests don't catch interface mismatches. Always add integration tests that verify real provider signatures match expected interface.
