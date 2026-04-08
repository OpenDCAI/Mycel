# Evaluation Persisted Source Truth Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace monitor’s hardcoded evaluation placeholder with real repo-backed persisted truth from `eval_runs/eval_metrics`.

**Architecture:** This plan is only `PR-D3a`. It introduces a narrow reader for the existing persisted eval source and wires `get_monitor_evaluation_truth()` to it. It does not implement runner writes, drilldown, or frontend work.

**Tech Stack:** Python, FastAPI service layer, pytest

---

## File Structure

- Modify: `backend/web/services/monitor_service.py`
  - add persisted source reader
  - connect `get_monitor_evaluation_truth()` to real source reading
- Modify: `tests/Unit/monitor/test_monitor_compat.py`
  - add no-runs and persisted-run tests
- Modify: `tests/Integration/test_monitor_resources_route.py`
  - prove route truth is no longer hardcoded

## Mandatory Boundary

- No frontend work
- No runner write-path activation
- No trace drilldown
- No product-facing evaluation work
- No schema redesign

## Task 1: Lock no-runs and persisted-run behavior

**Files:**
- Modify: `tests/Unit/monitor/test_monitor_compat.py`
- Test: `uv run pytest -q tests/Unit/monitor/test_monitor_compat.py -k 'evaluation_truth'`

- [ ] Add failing tests that prove:
  - wired eval storage with no runs returns explicit `idle/no_recorded_runs`
  - latest persisted run produces a truthful operator payload
- [ ] Run the targeted unit tests and verify the new expectations fail
- [ ] Commit:

```bash
git add tests/Unit/monitor/test_monitor_compat.py
git commit -m "test: lock evaluation persisted source truth"
```

## Task 2: Implement the persisted source reader

**Files:**
- Modify: `backend/web/services/monitor_service.py`
- Modify: `tests/Unit/monitor/test_monitor_compat.py`
- Test: `uv run pytest -q tests/Unit/monitor/test_monitor_compat.py -k 'evaluation_truth'`

- [ ] Add a small repo-backed reader using the existing eval store
- [ ] Keep the source contract minimal and truthful:
  - latest persisted run row
  - persisted metric rows for that run
- [ ] Make `get_monitor_evaluation_truth()`:
  - return explicit `idle/no_recorded_runs` when the source is wired but empty
  - fail loudly when repo reads or metric decoding break
  - feed only the fields that actually exist today into the operator payload
- [ ] Run targeted unit tests and verify they pass
- [ ] Commit:

```bash
git add backend/web/services/monitor_service.py tests/Unit/monitor/test_monitor_compat.py
git commit -m "feat: read persisted evaluation source for monitor truth"
```

## Task 3: Lock route-level truth upgrade

**Files:**
- Modify: `tests/Integration/test_monitor_resources_route.py`
- Test: `uv run pytest -q tests/Integration/test_monitor_resources_route.py -k 'monitor_evaluation or monitor_dashboard_route'`

- [ ] Add integration proof that:
  - `/api/monitor/evaluation` returns real persisted-source truth when a run exists
  - `/api/monitor/dashboard` derives evaluation summary from that same truth
- [ ] Run the targeted integration tests and verify they fail first if needed
- [ ] Make only the minimal backend adjustments needed to pass
- [ ] Re-run targeted integration tests and verify they pass
- [ ] Commit:

```bash
git add tests/Integration/test_monitor_resources_route.py backend/web/services/monitor_service.py backend/web/routers/monitor.py
git commit -m "test: lock monitor evaluation route to persisted source"
```

## Task 4: Verification and PR prep

**Files:**
- No required code files
- Update PR description/checkpoint as needed

- [ ] Run:
  - `uv run pytest -q tests/Unit/monitor/test_monitor_compat.py tests/Integration/test_monitor_resources_route.py`
  - `uv run ruff check backend/web/services/monitor_service.py tests/Unit/monitor/test_monitor_compat.py tests/Integration/test_monitor_resources_route.py`
- [ ] Record honest boundary:
  - this PR activates reader-side persisted truth only
  - live/in-flight runner activation is still `PR-D3b`
- [ ] Prepare draft PR as `PR-D3a`

## Hard Stopline

- This plan does not make the runner write live in-flight truth
- This plan does not add evaluation UI
- This plan does not add drilldown/history
- If the existing persisted eval source turns out not to be shared with web runtime, stop and write that source-gap down explicitly before coding
