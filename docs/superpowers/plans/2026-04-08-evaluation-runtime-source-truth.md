# Evaluation Runtime Source Truth Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace monitor’s hardcoded evaluation `unavailable` payload with a real file-backed runtime source that feeds the existing operator formatter.

**Architecture:** This plan is only `PR-D3a`. It introduces a narrow runtime source reader, validates the source, and wires `get_monitor_evaluation_truth()` to it. It does not implement runner writes, drilldown, or frontend work.

**Tech Stack:** Python, FastAPI service layer, pytest

---

## File Structure

- Modify: `backend/web/services/monitor_service.py`
  - add runtime source reader
  - add malformed-source failure path
  - connect `get_monitor_evaluation_truth()` to real source reading
- Modify: `tests/Unit/monitor/test_monitor_compat.py`
  - add source-absent, malformed-source, valid-source tests
- Modify: `tests/Integration/test_monitor_resources_route.py`
  - prove route truth is no longer hardcoded

## Mandatory Boundary

- No frontend work
- No runner write-path activation
- No trace drilldown
- No product-facing evaluation work
- No schema redesign

## Task 1: Lock source-absent and malformed-source behavior

**Files:**
- Modify: `tests/Unit/monitor/test_monitor_compat.py`
- Test: `uv run pytest -q tests/Unit/monitor/test_monitor_compat.py -k 'evaluation_truth'`

- [ ] Add failing tests that prove:
  - missing runtime source returns explicit `unavailable`
  - malformed runtime source raises loudly instead of silently downgrading to `unavailable`
  - valid runtime source produces a formatted operator payload
- [ ] Run the targeted unit tests and verify the new expectations fail
- [ ] Commit:

```bash
git add tests/Unit/monitor/test_monitor_compat.py
git commit -m "test: lock evaluation runtime source truth"
```

## Task 2: Implement the runtime source reader

**Files:**
- Modify: `backend/web/services/monitor_service.py`
- Modify: `tests/Unit/monitor/test_monitor_compat.py`
- Test: `uv run pytest -q tests/Unit/monitor/test_monitor_compat.py -k 'evaluation_truth'`

- [ ] Add a small file-backed runtime source reader
- [ ] Keep the source contract minimal:
  - `status`
  - `notes`
  - `score`
  - `threads`
- [ ] Make `get_monitor_evaluation_truth()`:
  - return explicit unavailable only when the source is absent
  - raise loudly when the source is malformed
  - feed valid source data into `build_evaluation_operator_surface(...)`
- [ ] Run targeted unit tests and verify they pass
- [ ] Commit:

```bash
git add backend/web/services/monitor_service.py tests/Unit/monitor/test_monitor_compat.py
git commit -m "feat: read evaluation runtime source for monitor truth"
```

## Task 3: Lock route-level truth upgrade

**Files:**
- Modify: `tests/Integration/test_monitor_resources_route.py`
- Test: `uv run pytest -q tests/Integration/test_monitor_resources_route.py -k 'monitor_evaluation or monitor_dashboard_route'`

- [ ] Add integration proof that:
  - `/api/monitor/evaluation` returns real source-backed truth when the source is present
  - `/api/monitor/dashboard` derives evaluation summary from that same truth
- [ ] Run the targeted integration tests and verify they fail first if needed
- [ ] Make only the minimal backend adjustments needed to pass
- [ ] Re-run targeted integration tests and verify they pass
- [ ] Commit:

```bash
git add tests/Integration/test_monitor_resources_route.py backend/web/services/monitor_service.py backend/web/routers/monitor.py
git commit -m "test: lock monitor evaluation route to runtime source"
```

## Task 4: Verification and PR prep

**Files:**
- No required code files
- Update PR description/checkpoint as needed

- [ ] Run:
  - `uv run pytest -q tests/Unit/monitor/test_monitor_compat.py tests/Integration/test_monitor_resources_route.py`
  - `uv run ruff check backend/web/services/monitor_service.py tests/Unit/monitor/test_monitor_compat.py tests/Integration/test_monitor_resources_route.py`
- [ ] Record honest boundary:
  - this PR activates reader-side runtime truth only
  - writer-side runner activation is still `PR-D3b`
- [ ] Prepare draft PR as `PR-D3a`

## Hard Stopline

- This plan does not make the runner write runtime source files
- This plan does not add evaluation UI
- This plan does not add drilldown/history
- If no existing evaluation runtime source path can be identified cleanly, stop and write the missing source-path contract explicitly before coding
