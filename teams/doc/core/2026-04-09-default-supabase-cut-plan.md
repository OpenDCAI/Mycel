# Default Supabase Cut Plan

Goal: make the code-level default strategy Supabase-first before claiming higher-level boot/runtime closure.

Current narrow ruling:

- Do not mix this slice with closure proof.
- Do not sweep all remaining SQLite callers.
- First cut only answers:
  - when `LEON_STORAGE_STRATEGY` is missing, what strategy does the code assume?
- After the first pass, the ruling tightened:
  - monitor default can safely move to Supabase-first
  - lease default cannot safely move yet
  - env-less sandbox control-plane still creates sqlite lease truth before strategy repos are available

First bounded slice:

1. `backend/web/services/monitor_service.py`
   - change missing-env fallback from `sqlite` to `supabase`
2. `sandbox/lease.py`
   - keep `_use_supabase_storage()` missing-env fallback at `sqlite`
   - add regression proving env-less `mark_needs_refresh()` still writes local sqlite lease state
3. add regression tests that pin the safe monitor default and the unsafe lease-default stopline

Evidence target:

- focused unit tests for:
  - `runtime_health_snapshot()` missing-env behavior
  - `_use_supabase_storage()` missing-env behavior
  - env-less `mark_needs_refresh()` local sqlite persistence
- full local unit files for:
  - `tests/Unit/monitor/test_monitor_compat.py`
  - `tests/Unit/sandbox/test_lease_probe_contract.py`

Stopline:

- after this slice, we can honestly say:
  - monitor read-surface default fallback is Supabase-first
  - lease default is still blocked by env-less sqlite control-plane ownership
- we still cannot honestly say:
  - code-level defaults are uniformly Supabase-first
  - the full system has boot/runtime closure without SQLite
- next move should be:
  - broader default/dev contract proof
  - especially README / quickstart / deployment / configuration docs plus queue / summary / langgraph dev startup paths
