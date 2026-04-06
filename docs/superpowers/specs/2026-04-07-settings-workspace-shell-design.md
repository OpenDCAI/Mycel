# Settings Workspace Shell Design

## Goal

Remove the repeated workspace-path normalization and recent-list update shell in `backend/web/routers/settings.py` without changing either route's contract.

## Scope

In scope:

- `POST /api/settings/workspace`
- `POST /api/settings/workspace/recent`

Out of scope:

- repo-backed persistence behavior
- local settings file persistence behavior
- default-model or model config endpoints

## Existing Problem

`set_default_workspace` and `add_recent_workspace` repeat two mechanical steps:

1. normalize a user-provided workspace path with `Path(...).expanduser().resolve()`
2. update `recent_workspaces` with dedupe + front-insert + max-five truncation

But the two routes do **not** share the same full contract:

- `set_default_workspace` has split validation messages:
  - `Workspace path does not exist`
  - `Workspace path is not a directory`
- `add_recent_workspace` collapses validation into:
  - `Invalid workspace path`
- `set_default_workspace` updates `default_workspace`
- `add_recent_workspace` must not update `default_workspace`

So the simplification must stay below those route-level semantics.

## Design

Keep the change inside `backend/web/routers/settings.py`.

Add two helpers:

```python
def _resolve_workspace_path_or_400(
    workspace: str,
    *,
    missing_detail: str,
    not_dir_detail: str,
) -> str:
    ...


def _remember_recent_workspace(settings: WorkspaceSettings, workspace_str: str) -> None:
    ...
```

The first helper only normalizes and validates the path, with route-provided error strings.

The second helper only mutates `recent_workspaces`:

- remove existing duplicate
- insert the workspace at the front
- truncate to five items

Routes remain responsible for their own semantics:

- `set_default_workspace` still sets `default_workspace`
- `add_recent_workspace` still leaves `default_workspace` untouched
- repo-vs-local persistence stays in each route

## Testing

Add focused tests in `tests/Integration/test_settings_workspace_router.py` that pin:

- path helper returns normalized workspace string
- path helper preserves route-provided validation messages
- recent helper dedupes and truncates
- `set_default_workspace` uses both helpers and still updates `default_workspace`
- `add_recent_workspace` uses both helpers and does not update `default_workspace`

These tests must stay on the router shell. They must not drift into persistence internals.

## Stopline

Do not:

- merge both routes into one helper-driven workflow
- let `add_recent_workspace` change `default_workspace`
- change repo/local branching
- flatten the two routes' validation messages into one contract
- move the helpers out of `settings.py`
