# Evaluation Runtime Writer Activation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make evaluation runs persist live `running` truth at start and finalize the same row at completion/cancellation/error.

**Architecture:** This plan keeps `PR-D3b` on the existing persisted source path introduced by `PR-D3a`. It adds minimal writer lifecycle methods for `eval_runs`, reuses the existing web `run_id` as the stable eval id, and keeps monitor/UI/product work out of scope.

**Tech Stack:** Python, FastAPI service layer, pytest, Supabase repo parity, SQLite repo parity

---

## File Structure

- Modify: `eval/tracer.py`
  - reuse caller-supplied `run_id`
- Modify: `storage/contracts.py`
  - extend `EvalRepo` protocol with minimal lifecycle writer methods
- Modify: `eval/repo.py`
  - SQLite lifecycle write parity
- Modify: `storage/providers/supabase/eval_repo.py`
  - Supabase lifecycle write parity
- Modify: `eval/storage.py`
  - expose lifecycle writer helpers through `TrajectoryStore`
- Modify: `backend/web/services/streaming_service.py`
  - write live `running` truth at start
  - finalize same row on completion/cancellation/error
- Modify: tests covering repo parity and streaming writer behavior

## Mandatory Boundary

- No frontend changes
- No monitor route changes
- No product behavior changes
- No new storage world
- No richer artifact/log/thread drilldown
- No fake live metrics beyond what already exists

## Task 1: Lock stable run-id reuse

**Files:**
- Modify: `tests/Unit/eval/test_tracer.py` or create it if absent
- Test: `uv run pytest -q tests/Unit/eval/test_tracer.py -k 'run_id'`

- [ ] Add a failing test that proves `TrajectoryTracer` preserves a caller-supplied `run_id`.
- [ ] Run the targeted test and verify it fails for the right reason.
- [ ] Implement the minimal tracer change to accept `run_id` and emit it in `RunTrajectory`.
- [ ] Re-run the targeted test and verify it passes.
- [ ] Commit:

```bash
git add eval/tracer.py tests/Unit/eval/test_tracer.py
git commit -m "test: lock evaluation tracer run id reuse"
```

## Task 2: Lock repo lifecycle writer parity

**Files:**
- Modify: `storage/contracts.py`
- Modify: `eval/repo.py`
- Modify: `storage/providers/supabase/eval_repo.py`
- Modify: parity tests near existing eval repo coverage
- Test:
  - `uv run pytest -q tests/Integration/test_storage_repo_abstraction_unification.py -k 'eval'`

- [ ] Add failing tests that prove both SQLite and Supabase eval repos support:
  - `upsert_run_header(...)`
  - `finalize_run(...)`
  - same-row lifecycle by shared `run_id`
- [ ] Run the targeted tests and verify they fail.
- [ ] Add the minimal protocol methods and provider implementations.
- [ ] Keep write semantics narrow:
  - run start upserts coarse row fields
  - terminal finalize updates row fields
  - no live incremental tool/llm row writes
- [ ] Re-run the targeted tests and verify they pass.
- [ ] Commit:

```bash
git add storage/contracts.py eval/repo.py storage/providers/supabase/eval_repo.py tests/Integration/test_storage_repo_abstraction_unification.py
git commit -m "feat: add evaluation lifecycle writer parity"
```

## Task 3: Expose lifecycle helpers through `TrajectoryStore`

**Files:**
- Modify: `eval/storage.py`
- Modify or create: `tests/Unit/eval/test_storage.py`
- Test: `uv run pytest -q tests/Unit/eval/test_storage.py`

- [ ] Add failing tests that prove `TrajectoryStore` exposes:
  - `upsert_run_header(...)`
  - `finalize_run(...)`
- [ ] Run the targeted test and verify it fails.
- [ ] Implement the smallest store helpers on top of the repo methods.
- [ ] Re-run the targeted test and verify it passes.
- [ ] Commit:

```bash
git add eval/storage.py tests/Unit/eval/test_storage.py
git commit -m "feat: expose evaluation lifecycle store helpers"
```

## Task 4: Activate writer-side live run persistence in streaming

**Files:**
- Modify: `backend/web/services/streaming_service.py`
- Modify or create targeted tests for streaming writer behavior
- Test:
  - `uv run pytest -q tests/Unit/backend/web/services/test_streaming_service.py -k 'evaluation or trajectory'`

- [ ] Add failing tests that prove:
  - a live `running` row is written when trajectory is enabled and the run starts
  - normal completion finalizes the same row id
  - cancellation/error finalizes the same row id with terminal status
- [ ] Run the targeted tests and verify they fail first.
- [ ] Implement the minimal streaming changes:
  - instantiate tracer with stable `run_id`
  - write `running` header before streaming begins
  - finalize same row on terminal completion
  - finalize same row on cancellation/error paths
- [ ] Re-run the targeted tests and verify they pass.
- [ ] Commit:

```bash
git add backend/web/services/streaming_service.py tests/Unit/backend/web/services/test_streaming_service.py
git commit -m "feat: persist live evaluation run lifecycle"
```

## Task 5: Lock monitor-visible live truth

**Files:**
- Modify: monitor integration tests
- Test:
  - `uv run pytest -q tests/Integration/test_monitor_resources_route.py tests/Unit/monitor/test_monitor_compat.py -k 'evaluation'`

- [ ] Add failing proof that a persisted `running` row now surfaces through the existing monitor evaluation truth path.
- [ ] Keep the assertion narrow:
  - same persisted source path
  - `status=running`
  - no fake artifact revival
- [ ] Re-run the targeted tests and verify they pass.
- [ ] Commit:

```bash
git add tests/Integration/test_monitor_resources_route.py tests/Unit/monitor/test_monitor_compat.py
git commit -m "test: lock live evaluation writer truth"
```

## Task 6: Verification and PR prep

**Files:**
- No required code files

- [ ] Run:
  - `uv run pytest -q tests/Unit/eval/test_tracer.py tests/Unit/eval/test_storage.py tests/Integration/test_storage_repo_abstraction_unification.py tests/Unit/backend/web/services/test_streaming_service.py tests/Unit/monitor/test_monitor_compat.py tests/Integration/test_monitor_resources_route.py`
  - `uv run ruff check eval/tracer.py eval/storage.py eval/repo.py storage/contracts.py storage/providers/supabase/eval_repo.py backend/web/services/streaming_service.py tests/Unit/eval/test_tracer.py tests/Unit/eval/test_storage.py tests/Integration/test_storage_repo_abstraction_unification.py tests/Unit/backend/web/services/test_streaming_service.py tests/Unit/monitor/test_monitor_compat.py tests/Integration/test_monitor_resources_route.py`
- [ ] Record honest boundary:
  - this PR activates writer-side live status only
  - richer artifacts/drilldown remain later work
- [ ] Prepare draft PR as `PR-D3b`

## Hard Stopline

- Do not add evaluation UI
- Do not add product-facing behavior
- Do not add a second live source contract
- Do not revive legacy manifest/log/thread-materialization fields unless a real writer exists for them
