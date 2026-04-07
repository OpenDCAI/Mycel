"""Cached resource overview snapshot with background refresh loop."""

from __future__ import annotations

import asyncio
import copy
import os
import threading
import time
from datetime import UTC, datetime
from typing import Any

from backend.web.services import resource_service

_DEFAULT_REFRESH_INTERVAL_SEC = 90.0

_snapshot_lock = threading.Lock()
_snapshot_cache: dict[str, Any] | None = None


def clear_resource_overview_cache() -> None:
    with _snapshot_lock:
        global _snapshot_cache
        _snapshot_cache = None


def clear_monitor_resource_overview_cache() -> None:
    clear_resource_overview_cache()


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _read_refresh_interval_sec() -> float:
    raw = (os.getenv("LEON_MONITOR_RESOURCES_REFRESH_SEC") or "").strip()
    if not raw:
        return _DEFAULT_REFRESH_INTERVAL_SEC
    value = float(raw)
    if value <= 0:
        raise RuntimeError("LEON_MONITOR_RESOURCES_REFRESH_SEC must be > 0")
    return value


def _with_refresh_metadata(
    payload: dict[str, Any],
    *,
    duration_ms: float,
    status: str,
    error: str | None,
) -> dict[str, Any]:
    summary = payload.setdefault("summary", {})
    snapshot_at = str(summary.get("snapshot_at") or _now_iso())
    summary["snapshot_at"] = snapshot_at
    summary["last_refreshed_at"] = snapshot_at
    summary["refresh_duration_ms"] = round(duration_ms, 1)
    summary["refresh_status"] = status
    summary["refresh_error"] = error
    return payload


def _snapshot_drifted_from_live_sessions(snapshot: dict[str, Any]) -> bool:
    live_stats = resource_service.visible_resource_session_stats()
    for provider in snapshot.get("providers") or []:
        provider_id = str(provider.get("id") or "")
        current = live_stats.get(provider_id, {"sessions": 0, "running": 0})
        cached_running = int(((provider.get("telemetry") or {}).get("running") or {}).get("used") or 0)
        cached_sessions = len(provider.get("sessions") or [])
        if cached_running != current["running"] or cached_sessions != current["sessions"]:
            return True
    for provider_id, current in live_stats.items():
        if current["running"] or current["sessions"]:
            cached = next((item for item in snapshot.get("providers") or [] if str(item.get("id") or "") == provider_id), None)
            if cached is None:
                return True
    return False


def refresh_resource_overview_sync() -> dict[str, Any]:
    """Refresh cached overview snapshot and return latest payload."""
    global _snapshot_cache
    started = time.perf_counter()
    try:
        payload = resource_service.list_resource_providers()
        duration_ms = (time.perf_counter() - started) * 1000
        payload = _with_refresh_metadata(payload, duration_ms=duration_ms, status="ok", error=None)
        with _snapshot_lock:
            _snapshot_cache = copy.deepcopy(payload)
        return payload
    except Exception as exc:
        duration_ms = (time.perf_counter() - started) * 1000
        error = str(exc)
        with _snapshot_lock:
            cached = copy.deepcopy(_snapshot_cache)
        if cached is None:
            raise
        degraded = _with_refresh_metadata(cached, duration_ms=duration_ms, status="error", error=error)
        with _snapshot_lock:
            _snapshot_cache = copy.deepcopy(degraded)
        return degraded


def refresh_monitor_resource_overview_sync() -> dict[str, Any]:
    return refresh_resource_overview_sync()


def get_resource_overview_snapshot() -> dict[str, Any]:
    """Return cached snapshot; perform one synchronous refresh on cold start."""
    with _snapshot_lock:
        cached = copy.deepcopy(_snapshot_cache)
    if cached is not None:
        # @@@resource-cache-live-drift - durable session truth lands in sandbox.db after a run
        # starts; if the cached Resources snapshot no longer matches visible lease/session
        # counts, refresh synchronously instead of serving a stale zero-sandbox card.
        if _snapshot_drifted_from_live_sessions(cached):
            return refresh_resource_overview_sync()
        return cached
    # @@@cold-start-cache-fill - route fallback fills cache once to keep first call deterministic.
    return refresh_resource_overview_sync()


def get_monitor_resource_overview_snapshot() -> dict[str, Any]:
    return get_resource_overview_snapshot()


async def resource_overview_refresh_loop() -> None:
    """Continuously refresh resource overview snapshot."""
    interval_sec = _read_refresh_interval_sec()
    while True:
        # @@@delayed-first-probe - avoid probe I/O at startup; keeps app boot and testclient deterministic.
        await asyncio.sleep(interval_sec)
        try:
            await asyncio.wait_for(
                asyncio.to_thread(resource_service.refresh_resource_snapshots),
                timeout=10.0,
            )
        except asyncio.CancelledError:
            raise
        except TimeoutError:
            print("[monitor] resource snapshot probe timeout")
        except Exception as exc:
            print(f"[monitor] resource snapshot probe error: {exc}")

        try:
            # @@@refresh-loop-timebox - provider SDK calls may block; timebox to keep shutdown responsive.
            await asyncio.wait_for(asyncio.to_thread(refresh_resource_overview_sync), timeout=10.0)
        except asyncio.CancelledError:
            raise
        except TimeoutError:
            print("[monitor] resource refresh loop timeout")
        except Exception as exc:
            print(f"[monitor] resource refresh loop error: {exc}")


async def monitor_resource_overview_refresh_loop() -> None:
    await resource_overview_refresh_loop()
