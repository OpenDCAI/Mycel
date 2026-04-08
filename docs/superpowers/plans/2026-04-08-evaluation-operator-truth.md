# Evaluation Operator Truth Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose a truthful monitor evaluation route and remove dashboard's hardcoded evaluation placeholders without pretending the evaluation runtime is already restored.

**Architecture:** This plan keeps the first evaluation recovery slice narrow. It introduces a dedicated monitor evaluation truth surface in backend code, makes dashboard derive summary from that same truth source, and encodes the current source-absent state as an explicit `unavailable` operator payload instead of `0 / None`. It does not restore evaluation UI or runtime activation.

**Tech Stack:** FastAPI, Python, pytest, monitor service/router layer

---

## File Structure

- Modify: `backend/web/services/monitor_service.py`
  - add the public evaluation truth helpers
  - add the explicit unavailable operator payload
  - add dashboard-summary derivation from operator truth
- Modify: `backend/web/routers/monitor.py`
  - add `GET /api/monitor/evaluation`
  - change dashboard route to consume evaluation summary from monitor service
- Modify: `tests/Unit/monitor/test_monitor_compat.py`
  - keep current operator-surface truth tests
  - add unit coverage for the new unavailable/operator-summary helpers
- Modify: `tests/Integration/test_monitor_resources_route.py`
  - extend monitor route smoke to cover `/api/monitor/evaluation`
  - prove dashboard no longer hardcodes `evaluations_running = 0` and `latest_evaluation = None`

## Mandatory Boundary

- No monitor frontend work
- No evaluation nav/page
- No runtime activation claims
- No product app changes
- No fake “empty but healthy” fallback

## Task 1: Add route-level failing tests for evaluation truth

**Files:**
- Modify: `tests/Integration/test_monitor_resources_route.py`
- Test: `uv run pytest -q tests/Integration/test_monitor_resources_route.py -k 'monitor_evaluation or monitor_dashboard_route'`

- [ ] **Step 1: Write the failing integration tests**

```python
def test_monitor_evaluation_route_exposes_operator_truth(monkeypatch):
    monkeypatch.setattr(
        monitor,
        "get_monitor_evaluation_truth",
        lambda: {
            "status": "unavailable",
            "kind": "unavailable",
            "tone": "warning",
            "headline": "Evaluation operator truth is not wired in this runtime yet.",
            "summary": "Monitor can report that evaluation truth is unavailable without pretending nothing is happening.",
            "facts": [{"label": "Status", "value": "unavailable"}],
            "artifacts": [],
            "artifact_summary": {"present": 0, "missing": 0, "total": 0},
            "next_steps": ["Restore a truthful evaluation runtime source before reviving the monitor evaluation page."],
            "raw_notes": None,
        },
    )

    with TestClient(_build_monitor_test_app()) as client:
        response = client.get("/api/monitor/evaluation")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "unavailable"
    assert payload["kind"] == "unavailable"
    assert payload["headline"] == "Evaluation operator truth is not wired in this runtime yet."
    assert payload["artifact_summary"] == {"present": 0, "missing": 0, "total": 0}


def test_monitor_dashboard_route_derives_evaluation_summary_from_service(monkeypatch):
    _stub_monitor_resource_snapshot(monkeypatch)
    monkeypatch.setattr(
        monitor_service,
        "get_monitor_evaluation_dashboard_summary",
        lambda: {
            "evaluations_running": 1,
            "latest_evaluation": {
                "status": "running",
                "kind": "running_active",
                "tone": "default",
                "headline": "Evaluation is actively running.",
            },
        },
    )

    with TestClient(_build_monitor_test_app()) as client:
        response = client.get("/api/monitor/dashboard")

    assert response.status_code == 200
    payload = response.json()
    assert payload["workload"]["evaluations_running"] == 1
    assert payload["latest_evaluation"] == {
        "status": "running",
        "kind": "running_active",
        "tone": "default",
        "headline": "Evaluation is actively running.",
    }
```

- [ ] **Step 2: Run the targeted integration tests to verify they fail**

Run:

```bash
uv run pytest -q tests/Integration/test_monitor_resources_route.py -k 'monitor_evaluation or monitor_dashboard_route'
```

Expected:
- FAIL because `backend.web.routers.monitor` does not expose `/api/monitor/evaluation`
- FAIL because dashboard still hardcodes `evaluations_running = 0` and `latest_evaluation = None`

- [ ] **Step 3: Commit the red test**

```bash
git add tests/Integration/test_monitor_resources_route.py
git commit -m "test: lock monitor evaluation truth routes"
```

## Task 2: Add the unavailable operator truth helpers

**Files:**
- Modify: `backend/web/services/monitor_service.py`
- Modify: `tests/Unit/monitor/test_monitor_compat.py`
- Test: `uv run pytest -q tests/Unit/monitor/test_monitor_compat.py -k 'evaluation_operator_surface or unavailable_evaluation'`

- [ ] **Step 1: Write the failing unit tests**

```python
def test_monitor_evaluation_truth_defaults_to_explicit_unavailable_surface():
    payload = monitor_service.get_monitor_evaluation_truth()

    assert payload["status"] == "unavailable"
    assert payload["kind"] == "unavailable"
    assert payload["tone"] == "warning"
    assert payload["headline"] == "Evaluation operator truth is not wired in this runtime yet."
    assert payload["artifact_summary"] == {
        "present": 0,
        "missing": 0,
        "total": 0,
    }
    assert payload["raw_notes"] is None


def test_monitor_evaluation_dashboard_summary_reduces_operator_truth():
    summary = monitor_service.build_monitor_evaluation_dashboard_summary(
        {
            "status": "running",
            "kind": "running_active",
            "tone": "default",
            "headline": "Evaluation is actively running.",
            "summary": "Long form summary that should not leak into dashboard shape.",
            "facts": [],
            "artifacts": [],
            "artifact_summary": {"present": 2, "missing": 1, "total": 3},
            "next_steps": [],
            "raw_notes": "runner=direct rc=0",
        }
    )

    assert summary == {
        "evaluations_running": 1,
        "latest_evaluation": {
            "status": "running",
            "kind": "running_active",
            "tone": "default",
            "headline": "Evaluation is actively running.",
        },
    }
```

- [ ] **Step 2: Run the targeted unit tests to verify they fail**

Run:

```bash
uv run pytest -q tests/Unit/monitor/test_monitor_compat.py -k 'evaluation_operator_surface or unavailable_evaluation'
```

Expected:
- FAIL because `get_monitor_evaluation_truth` and `build_monitor_evaluation_dashboard_summary` do not exist yet

- [ ] **Step 3: Write the minimal implementation**

Add this code to `backend/web/services/monitor_service.py` after `build_evaluation_operator_surface(...)`:

```python
def _evaluation_unavailable_surface() -> dict[str, Any]:
    return {
        "status": "unavailable",
        "kind": "unavailable",
        "tone": "warning",
        "headline": "Evaluation operator truth is not wired in this runtime yet.",
        "summary": (
            "Monitor can report that evaluation truth is unavailable without pretending nothing is happening."
        ),
        "facts": [{"label": "Status", "value": "unavailable"}],
        "artifacts": [],
        "artifact_summary": {"present": 0, "missing": 0, "total": 0},
        "next_steps": [
            "Restore a truthful evaluation runtime source before reviving the monitor evaluation page."
        ],
        "raw_notes": None,
    }


def get_monitor_evaluation_truth() -> dict[str, Any]:
    # @@@evaluation-truth-stopline - PR-D1 exposes explicit unavailable truth until a real runtime source is wired.
    return _evaluation_unavailable_surface()


def build_monitor_evaluation_dashboard_summary(payload: dict[str, Any]) -> dict[str, Any]:
    status = str(payload.get("status") or "unavailable")
    return {
        "evaluations_running": 1 if status == "running" else 0,
        "latest_evaluation": {
            "status": status,
            "kind": payload.get("kind"),
            "tone": payload.get("tone"),
            "headline": payload.get("headline"),
        },
    }


def get_monitor_evaluation_dashboard_summary() -> dict[str, Any]:
    return build_monitor_evaluation_dashboard_summary(get_monitor_evaluation_truth())
```

- [ ] **Step 4: Run the targeted unit tests to verify they pass**

Run:

```bash
uv run pytest -q tests/Unit/monitor/test_monitor_compat.py -k 'evaluation_operator_surface or unavailable_evaluation'
```

Expected:
- PASS

- [ ] **Step 5: Commit**

```bash
git add backend/web/services/monitor_service.py tests/Unit/monitor/test_monitor_compat.py
git commit -m "feat: add monitor evaluation truth helpers"
```

## Task 3: Expose the monitor evaluation route and rewire dashboard

**Files:**
- Modify: `backend/web/routers/monitor.py`
- Modify: `tests/Integration/test_monitor_resources_route.py`
- Test: `uv run pytest -q tests/Integration/test_monitor_resources_route.py -k 'monitor_evaluation or monitor_dashboard_route'`

- [ ] **Step 1: Write the minimal router implementation**

Update `backend/web/routers/monitor.py` like this:

```python
@router.get("/evaluation")
def evaluation_snapshot():
    return monitor_service.get_monitor_evaluation_truth()


@router.get("/dashboard")
def dashboard_snapshot():
    health = monitor_service.runtime_health_snapshot()
    resources = get_monitor_resource_overview_snapshot()
    leases = list_leases()
    evaluation = monitor_service.get_monitor_evaluation_dashboard_summary()

    resource_summary = resources.get("summary") or {}
    lease_summary = leases.get("summary") or {}

    return {
        "snapshot_at": health.get("snapshot_at"),
        "resources_summary": resource_summary,
        "infra": {
            "providers_active": int(resource_summary.get("active_providers") or 0),
            "providers_unavailable": int(resource_summary.get("unavailable_providers") or 0),
            "leases_total": int(lease_summary.get("total") or leases.get("count") or 0),
            "leases_diverged": int(lease_summary.get("diverged") or 0) + int(lease_summary.get("orphan_diverged") or 0),
            "leases_orphan": int(lease_summary.get("orphan") or 0) + int(lease_summary.get("orphan_diverged") or 0),
            "leases_healthy": int(lease_summary.get("healthy") or 0),
        },
        "workload": {
            "db_sessions_total": int(((health.get("db") or {}).get("counts") or {}).get("chat_sessions") or 0),
            "provider_sessions_total": int(((health.get("sessions") or {}).get("total")) or 0),
            "running_sessions": int(resource_summary.get("running_sessions") or 0),
            "evaluations_running": int(evaluation["evaluations_running"]),
        },
        "latest_evaluation": evaluation["latest_evaluation"],
    }
```

- [ ] **Step 2: Run the targeted integration tests**

Run:

```bash
uv run pytest -q tests/Integration/test_monitor_resources_route.py -k 'monitor_evaluation or monitor_dashboard_route'
```

Expected:
- PASS

- [ ] **Step 3: Run the broader monitor route pack**

Run:

```bash
uv run pytest -q tests/Integration/test_monitor_resources_route.py tests/Unit/monitor/test_monitor_compat.py
```

Expected:
- PASS

- [ ] **Step 4: Commit**

```bash
git add backend/web/routers/monitor.py tests/Integration/test_monitor_resources_route.py
git commit -m "feat: expose monitor evaluation truth route"
```

## Task 4: Tighten docs and verification proof

**Files:**
- Modify: `docs/superpowers/specs/2026-04-08-evaluation-operator-truth-design.md` only if implementation diverged
- Update: `/Users/lexicalmathical/Codebase/algorithm-repos/mysale-cca/rebuild-agent-core/checkpoints/architecture/cc-core-contract-alignment-2026-04-05.md`

- [ ] **Step 1: Run final verification**

Run:

```bash
uv run pytest -q tests/Unit/monitor/test_monitor_compat.py tests/Integration/test_monitor_resources_route.py
```

Expected:
- PASS

- [ ] **Step 2: Record the delivered truth in checkpoint**

Append this kind of entry to the external checkpoint:

```md
- latest-delta-2026-04-08-pr-d1-landed:
  - `/api/monitor/evaluation` now exposes explicit operator truth
  - current source-absent state is encoded as `status=unavailable`, not `0 / None`
  - dashboard evaluation summary is now derived from the same truth source
```

- [ ] **Step 3: Commit any doc/update drift**

```bash
git add -f docs/superpowers/specs/2026-04-08-evaluation-operator-truth-design.md
git commit -m "docs: record evaluation truth delivery"
```

## Verification Standard

- `uv run pytest -q tests/Unit/monitor/test_monitor_compat.py -k 'evaluation_operator_surface or unavailable_evaluation'`
- `uv run pytest -q tests/Integration/test_monitor_resources_route.py -k 'monitor_evaluation or monitor_dashboard_route'`
- `uv run pytest -q tests/Unit/monitor/test_monitor_compat.py tests/Integration/test_monitor_resources_route.py`

## Hard Stopline

- This plan does not revive an evaluation page
- This plan does not revive evaluation nav
- This plan does not claim the evaluation runtime is healthy or restored
- This plan only replaces fake dashboard placeholders with explicit operator truth
