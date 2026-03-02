# Multi-Root Workspace Security Boundary

## Problem

Local provider's agent can't access uploaded thread files. Thread files live at `~/.leon/thread_files/{tid}/files/`, but the agent's workspace boundary is the project directory. Security middleware correctly blocks cross-boundary access. Remote providers solve this by mounting/copying files INTO the sandbox — local has no equivalent.

## Solution

Extend the security boundary from a single `workspace_root` to a list: primary workspace + extra allowed paths. For local provider, auto-include the thread files dir. Make `allowed_paths` configurable in sandbox config JSON (surfaced in frontend settings).

## Changes

### 1. Security middleware: accept `extra_allowed_paths`

**`core/filesystem/middleware.py` — `FileSystemMiddleware`:**

Add `extra_allowed_paths: list[Path] = []` to `__init__`. In `_validate_path()`, after failing `relative_to(workspace_root)`, check each extra path:

```python
def _validate_path(self, path, operation):
    resolved = Path(path) if self.backend.is_remote else Path(path).resolve()
    # Primary workspace
    try:
        resolved.relative_to(self.workspace_root)
        return True, "", resolved
    except ValueError:
        pass
    # Extra allowed paths
    for allowed in self.extra_allowed_paths:
        try:
            resolved.relative_to(allowed)
            return True, "", resolved
        except ValueError:
            pass
    return False, f"Path outside workspace\n   Workspace: {self.workspace_root}\n   Attempted: {resolved}", None
```

**`core/command/hooks/path_security.py` — `PathSecurityHook`:**

Same pattern in `_is_within_workspace()`:

```python
def _is_within_workspace(self, path: Path) -> bool:
    try:
        path.resolve().relative_to(self.workspace_root)
        return True
    except ValueError:
        pass
    for allowed in self.extra_allowed_paths:
        try:
            path.resolve().relative_to(allowed)
            return True
        except ValueError:
            pass
    return False
```

### 2. LeonAgent: thread through `extra_allowed_paths`

**`agent.py`:**

Accept `extra_allowed_paths: list[Path | str] = []` in `__init__`. Store as `self.extra_allowed_paths`. Pass to `_add_filesystem_middleware()` and `_add_command_middleware()`.

### 3. agent_pool: pass thread files dir for local provider

**`backend/web/services/agent_pool.py`:**

Currently the file-mount block is skipped for local (`if sandbox_type != "local"`). Change to: for local, pass the thread files path as `extra_allowed_paths` to `create_agent_sync()`.

```python
# For all providers: ensure thread files exist
channel = ensure_thread_files(thread_id, workspace_id=workspace_id)

if sandbox_type == "local":
    # Local: add thread files dir to allowed paths (no mount needed)
    extra_allowed_paths = [channel["files_path"]]
else:
    # Remote: mount/copy files into sandbox
    # ... existing mount logic ...
```

### 4. SandboxConfig: add `allowed_paths`

**`sandbox/config.py` — `SandboxConfig`:**

```python
class SandboxConfig(BaseModel):
    ...
    allowed_paths: list[str] = Field(default_factory=list)
```

When loading config in `sandbox_service.py`, pass `allowed_paths` through to agent creation. These are resolved to absolute paths and added to `extra_allowed_paths`.

The `save()` method already serializes all fields. The settings API (`GET/POST /api/settings/sandboxes`) passes raw JSON, so `allowed_paths` is automatically supported.

### 5. Frontend

The sandbox settings UI reads/writes sandbox config JSON. Adding `allowed_paths` to the JSON schema means it appears in the config editor. No backend route changes needed — `SandboxConfigRequest.config` is an untyped dict.

## Data Flow

```
Thread creation
  → ensure_thread_files(tid) → ~/.leon/thread_files/{tid}/files/
  → create_agent_sync(extra_allowed_paths=[files_dir] + config.allowed_paths)
    → LeonAgent(extra_allowed_paths=...)
      → FileSystemMiddleware(extra_allowed_paths=...)
      → PathSecurityHook(extra_allowed_paths=...)

Agent reads file at ~/.leon/thread_files/{tid}/files/test.txt
  → _validate_path() checks workspace_root → FAIL
  → checks extra_allowed_paths → PASS (thread files dir matches)
  → file read succeeds
```

## What doesn't change

- `workspace_root` semantics unchanged
- Remote provider mount/copy logic unchanged
- Thread files storage location unchanged
- Existing security for unknown paths still blocked
