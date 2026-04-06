# ToolRunner Single Async Path Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Collapse `ToolRunner`'s duplicated sync/async private execution stack into one async-first core while preserving the public middleware contract.

**Architecture:** Keep `wrap_tool_call(...)` and `awrap_tool_call(...)`, but move validation, hook execution, permission resolution, and handler dispatch into one shared async path. The sync wrapper becomes a thin bridge to that async core instead of maintaining separate private twins.

**Tech Stack:** Python, asyncio, pytest, pyright, ruff

---

### Task 1: Lock the shared-core seam with failing tests

**Files:**
- Modify: `tests/Unit/core/test_tool_registry_runner.py`
- Read: `core/runtime/runner.py`

- [ ] **Step 1: Write one failing sync-wrapper proof**

Add a focused test that patches a new async core helper and proves `wrap_tool_call(...)` routes through it instead of separate sync-specific validation/permission/hook helpers.

- [ ] **Step 2: Run the focused test to verify RED**

Run:

```bash
uv run pytest tests/Unit/core/test_tool_registry_runner.py -k 'sync_wrap_tool_call_uses_shared_async_core' -q
```

Expected: FAIL because `wrap_tool_call(...)` still owns its own sync path.

### Task 2: Collapse private helper twins into async-first helpers

**Files:**
- Modify: `core/runtime/runner.py`

- [ ] **Step 1: Introduce one async core helper**

Extract one async helper that owns:

- schema validation
- tool-specific validation
- pre-tool hook execution
- permission resolution
- handler dispatch
- result normalization/materialization

- [ ] **Step 2: Collapse hook/permission helper twins**

Remove the paired sync variants by keeping only async-first helpers for:

- result hooks
- permission consumption
- permission request
- tool-specific validation
- pre-tool hooks
- permission resolution

If sync callers still need them, they should go through one outer bridge.

- [ ] **Step 3: Preserve sync wrapper as a thin bridge**

Make `wrap_tool_call(...)` delegate to the async core through one narrow bridge instead of its own twin stack.

### Task 3: Preserve live behavior and verify

**Files:**
- Modify: `tests/Unit/core/test_tool_registry_runner.py`

- [ ] **Step 1: Run focused ToolRunner proofs**

Run:

```bash
uv run pytest tests/Unit/core/test_tool_registry_runner.py -k 'sync_wrap_tool_call or awrap_tool_call' -q
```

Expected: PASS

- [ ] **Step 2: Run touched static checks**

Run:

```bash
uv run pyright core/runtime/runner.py tests/Unit/core/test_tool_registry_runner.py
uv run ruff check core/runtime/runner.py tests/Unit/core/test_tool_registry_runner.py
uv run ruff format --check core/runtime/runner.py tests/Unit/core/test_tool_registry_runner.py
```

Expected: all green

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/specs/2026-04-07-toolrunner-single-async-path-design.md docs/superpowers/plans/2026-04-07-toolrunner-single-async-path.md core/runtime/runner.py tests/Unit/core/test_tool_registry_runner.py
git commit -m "refactor: collapse tool runner sync twins"
```
