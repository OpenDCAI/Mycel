# Default Supabase Cut Plan

Goal: make the code-level default strategy Supabase-first before claiming higher-level boot/runtime closure.

Current narrow ruling:

- Do not mix this slice with closure proof.
- Do not sweep all remaining SQLite callers.
- First cut only answers:
  - when `LEON_STORAGE_STRATEGY` is missing, what strategy does the code assume?

First bounded slice:

1. `backend/web/services/monitor_service.py`
   - change missing-env fallback from `sqlite` to `supabase`
2. `sandbox/lease.py`
   - change `_use_supabase_storage()` missing-env fallback from `sqlite` to `supabase`
3. add regression tests that pin both defaults

Evidence target:

- focused unit tests for:
  - `runtime_health_snapshot()` missing-env behavior
  - `_use_supabase_storage()` missing-env behavior
- full local unit files for:
  - `tests/Unit/monitor/test_monitor_compat.py`
  - `tests/Unit/sandbox/test_lease_probe_contract.py`

Stopline:

- after this slice, we can honestly say:
  - code-level default fallback is Supabase-first
- we still cannot honestly say:
  - the full system has boot/runtime closure without SQLite
- next move should be:
  - broader default/dev contract proof
  - or `CP05 Closure Proof`
