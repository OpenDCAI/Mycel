# ToolRunner Single Async Path Design

**Date:** 2026-04-07
**Branch:** `dev`

## Goal

Collapse `ToolRunner`'s duplicated sync/async execution twins into one async core path, while preserving the existing middleware-facing public contract.

This slice is about ownership and execution shape, not changing permission policy or tool semantics.

## Scope

This design covers:

- `core/runtime/runner.py`
- `core/runtime/registry.py` if handler normalization is needed there
- focused `tests/Unit/core/test_tool_registry_runner.py` coverage

This design does **not** cover:

- changing `ToolRunner`'s public `wrap_tool_call` / `awrap_tool_call` surface today
- changing permission precedence
- changing hook semantics
- rewriting `SpillBufferMiddleware` or other middleware consumers
- broader tool registry redesign

## Current Facts

### 1. `ToolRunner` still has large sync/async twin stacks

Current `core/runtime/runner.py` still maintains paired methods for the same behavior:

- `_apply_result_hooks_sync` / `_apply_result_hooks`
- `_consume_permission_resolution_sync` / `_consume_permission_resolution_async`
- `_request_permission_sync` / `_request_permission_async`
- `_run_tool_specific_validation_sync` / `_run_tool_specific_validation_async`
- `_run_pre_tool_use_sync` / `_run_pre_tool_use_async`
- `_resolve_permission` / `_resolve_permission_async`
- `_validate_and_run` / `_validate_and_run_async`

That is the real seam, not just sync vs async handler invocation.

### 2. The sync path still bridges async work through `_run_awaitable_sync(...)`

`_run_awaitable_sync(...)` starts a daemon thread and runs `asyncio.run(...)` inside it when a loop is already active.

That bridge is the current escape hatch for:

- async permission checkers
- async pre/post hooks
- async permission request hooks

It works, but it is the footgun named in the issue.

### 3. The async path already encodes the honest runtime behavior

The live product path mostly uses `awrap_tool_call(...)`, and the async side already contains the more honest execution rule:

- sync handlers are offloaded via `asyncio.to_thread(...)`
- async handlers are awaited directly
- async hooks stay inside one event loop

That means the async path is the better core to keep.

### 4. The sync middleware surface still has consumers

Tests still call `runner.wrap_tool_call(...)` directly, and middleware contracts elsewhere in the repo still expose sync wrappers.

So this slice should **not** delete the public sync wrapper outright unless a broader middleware contract change is planned.

## Problem

Right now `ToolRunner` owns the same policy twice:

1. validate args
2. run pre-tool hooks
3. resolve permission
4. execute handler
5. run post hooks
6. materialize result

Once for sync, once for async.

That causes three costs:

- policy drift risk between the twins
- more tests for the same behavior
- reliance on `_run_awaitable_sync(...)` whenever sync wrappers encounter async hooks or permission checks

The current code works, but the ownership is still wrong.

## Chosen Approach

Move `ToolRunner` to one async execution core and make the sync wrapper a thin bridge.

The intended shape is:

- one async helper stack for validation / hooks / permission / dispatch / result shaping
- `awrap_tool_call(...)` uses that core directly
- `wrap_tool_call(...)` calls the same async core through one outer bridge instead of maintaining its own twin stack

This is narrower and safer than trying to normalize every tool handler at registry registration time in the first slice.

## Intended Backend Shape

### 1. Keep public middleware methods stable

Keep:

- `wrap_model_call(...)`
- `awrap_model_call(...)`
- `wrap_tool_call(...)`
- `awrap_tool_call(...)`

Do not widen the blast radius into middleware interface changes.

### 2. Make one async core own the entire tool flow

Introduce one async core helper that owns:

- schema validation
- tool-specific validation
- pre-tool hooks
- permission resolution
- handler dispatch
- post-hook application
- materialization

The sync wrapper should no longer call sync-specific twins for these phases.

### 3. Keep handler offload semantics in the async core

The async core should preserve the current honest rule:

- if handler is async, `await` it
- if handler is sync, `await asyncio.to_thread(...)`

Do not fall back to direct sync execution on the web event loop.

### 4. Collapse hook/permission helper twins behind async helpers

Helpers like:

- permission consumption
- permission request creation
- hook execution
- tool-specific validation

should become async-first helpers.

If the sync wrapper still needs them, it should call the async helper through one narrow bridge instead of owning its own duplicate implementation.

### 5. Preserve observable policy

This slice must preserve:

- permission precedence
- ask/deny/allow materialization
- route-visible error messages
- hook timeout behavior
- MCP/local result materialization order

This is a structural simplification slice, not a policy change.

## Non-Goals

- do not redesign `ToolRegistry` unless a tiny helper is strictly needed
- do not change `SpillBufferMiddleware`
- do not remove sync middleware methods repo-wide
- do not change how permission prompts are worded
- do not broaden into runtime/model changes

## Testing Strategy

### Required proof

- one red/green test that proves sync `wrap_tool_call(...)` now routes through the shared async core instead of separate sync twins
- existing sync-wrapper tests for async permission/hook behavior stay green
- focused `awrap_tool_call(...)` tests stay green

### Useful red tests

- sync wrapper still honors async permission checker inside a running event loop
- sync wrapper still honors async post hook timeout
- sync wrapper still keeps request-hook precedence before permission prompt

### Stopline

This slice stops when:

- the private sync/async twin helpers are collapsed into one async-first core
- `wrap_tool_call(...)` becomes a thin bridge
- focused ToolRunner tests stay green

It must **not** expand into:

- middleware interface redesign
- registry-wide tool metadata cleanup
- permission policy rewrites
- unrelated tool subsystem refactors
