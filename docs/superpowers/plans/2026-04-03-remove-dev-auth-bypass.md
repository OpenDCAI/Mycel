# Remove Dev Auth Bypass Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove frontend/backend dev auth bypass completely and keep development convenience outside runtime auth code.

**Architecture:** Delete bypass branches instead of adding handshake logic. Keep runtime auth single-path and move developer convenience into an external helper script that talks to the real auth endpoints.

**Tech Stack:** FastAPI, Zustand, pytest, small Python helper script

---

### Task 1: Delete Backend Bypass Path

**Files:**
- Modify: `backend/web/core/dependencies.py`
- Modify: `backend/web/routers/auth.py`
- Modify: `tests/test_auth_router.py`

- [ ] Remove `_DEV_SKIP_AUTH`, `_DEV_PAYLOAD`, and `is_dev_skip_auth_enabled()` from backend auth dependencies.
- [ ] Make `register/login` routers always call the real auth service.
- [ ] Replace bypass-specific tests with direct auth-router behavior tests.

### Task 2: Delete Frontend Bypass Path

**Files:**
- Modify: `frontend/app/src/store/auth-store.ts`

- [ ] Remove `VITE_DEV_SKIP_AUTH`, `DEV_MOCK_USER`, and bypass-specific persisted merge logic.
- [ ] Keep auth store empty-by-default until real login/register succeeds.
- [ ] Make `401` always clear auth state.

### Task 3: Add External Dev Helper

**Files:**
- Create: `scripts/dev/register_and_login.py`

- [ ] Add a small script that calls `/api/auth/register` then `/api/auth/login`.
- [ ] Print token/user/entity info for local debugging.
- [ ] Keep it outside runtime code paths.

### Task 4: Verify Real Auth End To End

**Files:**
- Modify: `tests/test_auth_router.py`
- Verify live backend manually

- [ ] Run focused backend tests.
- [ ] Run related auth + caller-contract regressions.
- [ ] Verify register -> login -> create thread -> send message against the live backend.

### Task 5: Sync Checkpoints

**Files:**
- Modify: `/Users/lexicalmathical/Codebase/algorithm-repos/mysale-cca/rebuild-agent-core/checkpoints/architecture/new_updates.md`
- Modify: `/Users/lexicalmathical/Codebase/algorithm-repos/mysale-cca/rebuild-agent-core/briefing.md`
- Modify: `/Users/lexicalmathical/Codebase/algorithm-repos/mysale-cca/rebuild-agent-core/todo/index.md`

- [ ] Rewrite `nu-04` from “auth-mode handshake mismatch” to “bypass removed by design”.
- [ ] Note the dev helper as tooling, not runtime contract.
- [ ] Tell hostile reviewer the old bypass assumptions are obsolete.
