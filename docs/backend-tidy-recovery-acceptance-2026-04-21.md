# Backend Tidy Recovery Acceptance

## Purpose

This note is the local acceptance contract for `backend-tidy-break`.

Its job is to prevent us from confusing:

- structural break success
- import rewrites
- layout-checker progress
- low-value test greenness

with actual recovery.

If you remember only one note, remember this one. It links to the full design set.

## Full doc set

Primary design truth:

- `/Users/lexicalmathical/Codebase/mycel-db-design/program/doc/core/backend-domain-target-architecture-2026-04-19.md`
- `/Users/lexicalmathical/Codebase/mycel-db-design/program/doc/core/backend-tidy-migration-plan-2026-04-20.md`
- `/Users/lexicalmathical/Codebase/mycel-db-design/program/doc/core/backend-package-dependencies-2026-04-20.md`
- `/Users/lexicalmathical/Codebase/mycel-db-design/program/doc/core/backend-external-boundary-convergence-2026-04-21.md`

Tactical handoff docs:

- `/Users/lexicalmathical/share/tasks/backend-tidy/_index.md`
- `/Users/lexicalmathical/share/tasks/backend-tidy/recovery-task-break-1.md`
- `/Users/lexicalmathical/share/tasks/backend-tidy/recovery-task-break-2.md`
- `/Users/lexicalmathical/share/tasks/backend-tidy/recovery-task-break-3.md`

## Core ruling

`backend-tidy-break` is a break-and-recover line.

That means:

- the break is allowed to shatter imports and tests
- the checker only proves the break landed hard enough
- recovery is only complete when the real Mycel product paths work again

## What does not count as recovery

These are useful signals, but not completion:

- `scripts/tidy/check_backend_layout.py` passing
- `backend.web.main` importing
- `backend.monitor_app.main` importing
- pytest collection becoming clean
- unit tests passing
- source-guard or owner-shell tests passing

## What does count as recovery

Remote `dev` should satisfy all of these:

- `monitor` behaves as an independent backend, not via dead compat shells
- `chat` behaves as an independent backend, not via dead compat shells
- Mycel agent can initialize successfully
- Mycel agent can complete a real minimal turn
- subagent tooling works
- marketplace skill download / install works
- directory structure matches target layout
- dependency edges match the intended package boundaries

## Cognitive risks

### Risk 1: Mistaking structure for recovery

Symptom:
- "checker is mostly green, so recover is mostly done"

Countermeasure:
- require product/runtime proof, not just structural proof

### Risk 2: Mistaking importability for system health

Symptom:
- "`backend.web.main` imports, so recover is done"

Countermeasure:
- import sanity is only a checkpoint, never the finish line

### Risk 3: Letting low-value tests steer the lane

Symptom:
- preserving owner/compat/source-guard tests becomes the main work

Countermeasure:
- keep high-value behavior tests
- delete or downgrade low-value shell/owner/source-guard tests

### Risk 4: Mixing mainline and sidecar work

Symptom:
- backend recovery and external-boundary convergence blur together

Countermeasure:
- mainline:
  backend-tidy-break recovery inside `backend/**`
- sidecar:
  outer-package boundary convergence outside the main backend write set

### Risk 5: Confusing env blockers with recovery blockers

Symptom:
- a runtime smoke fails and we immediately treat it as proof the code is still broken

Countermeasure:
- classify each failure:
  code-path break vs env/config absence vs external outage

## Operational checkpoint questions

Before claiming progress, answer:

- what real runtime/product surface moved forward?
- what is still only structural evidence?
- what is still blocked by code?
- what is blocked by env/config?
- did low-value cleanup try to hijack the lane?

## Stopline

Do not claim recovery complete because:

- the break landed
- imports were rewired
- checker passed
- collection passed
- some unit tests passed

Completion is defined by restored product truth plus correct final structure.
