# Closure Proof Plan

Goal: prove the Supabase runtime contract with caller-level evidence instead of assuming that earlier abstraction work already removed SQLite from the critical path.

Current narrow ruling:

- Do not jump straight to "Supabase-only boot is done".
- First prove that explicit `LEON_STORAGE_STRATEGY=supabase` does not silently route sandbox control-plane repo construction back through SQLite on the default sandbox path.
- Keep custom/local `db_path` semantics intact for harnesses and explicit local callers.

First bounded slice:

1. `sandbox/control_plane_repos.py`
   - add the smallest strategy gate:
     - if strategy is explicit `supabase`
     - and the target db path matches the canonical default sandbox db path
     - use runtime builders for:
       - chat session repo
       - lease repo
       - terminal repo
2. `tests/Unit/sandbox/test_manager_repo_strategy.py`
   - prove `SandboxManager(provider=...)` now gets strategy repos under explicit Supabase
   - prove `SandboxManager(provider=..., db_path=custom)` still gets sqlite repos

Evidence target:

- focused control-plane caller proof:
  - `uv run pytest -q tests/Unit/sandbox/test_manager_repo_strategy.py`
- adjacent manager regression guard:
  - `uv run pytest -q tests/Unit/sandbox/test_sandbox_manager_volume_repo.py`
- source-level hygiene:
  - `uv run ruff check sandbox/control_plane_repos.py tests/Unit/sandbox/test_manager_repo_strategy.py`
  - `uv run python -m py_compile sandbox/control_plane_repos.py tests/Unit/sandbox/test_manager_repo_strategy.py`

Stopline:

- after this slice, we can honestly say:
  - explicit Supabase + default sandbox path no longer forces sqlite control-plane repo construction
  - custom `db_path` still preserves local sqlite semantics
- after the follow-up proof, we can also honestly say:
  - missing `LEON_STORAGE_STRATEGY` still keeps the default sandbox control-plane on sqlite truth
- we still cannot honestly say:
  - env-less sandbox control-plane is closed
  - the whole system boots without SQLite
  - real product Supabase closure proof is complete

Default next move:

- continue `CP05` with the next narrow proof:
  - env-less sandbox control-plane residual narrowing
  - or another concrete default-boot blocker if it appears first in caller-level evidence
