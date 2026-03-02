# Multi-Root Workspace Security Boundary — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Allow the local provider's agent to access thread files by extending the security boundary from a single workspace_root to a list of allowed paths.

**Architecture:** Add `extra_allowed_paths: list[Path]` to `FileSystemMiddleware` and `PathSecurityHook`. Auto-inject the thread files dir for local provider in `agent_pool.py`. Add `allowed_paths` field to `SandboxConfig` for user-configurable extra paths.

**Tech Stack:** Python, Pydantic, pytest

---

### Task 1: Extend PathSecurityHook with extra_allowed_paths

**Files:**
- Modify: `core/command/hooks/path_security.py`
- Test: `tests/test_path_security_extra_paths.py`

**Step 1: Write the failing test**

Create `tests/test_path_security_extra_paths.py`:

```python
from pathlib import Path
import pytest
from core.command.hooks.path_security import PathSecurityHook


def test_extra_allowed_path_permits_access(tmp_path: Path) -> None:
    workspace = tmp_path / "project"
    workspace.mkdir()
    extra = tmp_path / "thread_files"
    extra.mkdir()

    hook = PathSecurityHook(workspace_root=workspace, extra_allowed_paths=[extra])
    result = hook.check_command(f"cat {extra}/test.txt", {})
    assert result.allow


def test_extra_allowed_path_blocks_unrelated(tmp_path: Path) -> None:
    workspace = tmp_path / "project"
    workspace.mkdir()
    extra = tmp_path / "thread_files"
    extra.mkdir()
    unrelated = tmp_path / "secrets"
    unrelated.mkdir()

    hook = PathSecurityHook(workspace_root=workspace, extra_allowed_paths=[extra])
    result = hook.check_command(f"cat {unrelated}/secret.txt", {})
    assert not result.allow


def test_no_extra_paths_preserves_existing_behavior(tmp_path: Path) -> None:
    workspace = tmp_path / "project"
    workspace.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()

    hook = PathSecurityHook(workspace_root=workspace)
    result = hook.check_command(f"cat {outside}/file.txt", {})
    assert not result.allow
```

**Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/test_path_security_extra_paths.py -v`
Expected: FAIL — `PathSecurityHook.__init__() got an unexpected keyword argument 'extra_allowed_paths'`

**Step 3: Implement**

Edit `core/command/hooks/path_security.py`:

```python
class PathSecurityHook(BashHook):
    """Path security hook - prevents directory traversal and access outside workspace."""

    priority = 10
    name = "PathSecurity"
    description = "Restrict bash commands to workspace directory only"

    def __init__(self, workspace_root: Path | str | None = None, strict_mode: bool = True, extra_allowed_paths: list[Path | str] | None = None, **kwargs):
        super().__init__(workspace_root, **kwargs)

        if workspace_root is None:
            raise ValueError("PathSecurityHook requires workspace_root")

        self.strict_mode = strict_mode
        self.extra_allowed_paths: list[Path] = [Path(p).resolve() for p in (extra_allowed_paths or [])]

    # ... check_command unchanged ...

    def _is_within_workspace(self, path: Path) -> bool:
        resolved = path.resolve()
        try:
            resolved.relative_to(self.workspace_root)
            return True
        except ValueError:
            pass
        for allowed in self.extra_allowed_paths:
            try:
                resolved.relative_to(allowed)
                return True
            except ValueError:
                pass
        return False
```

**Step 4: Run test to verify it passes**

Run: `uv run python -m pytest tests/test_path_security_extra_paths.py -v`
Expected: 3 passed

**Step 5: Commit**

```bash
git add core/command/hooks/path_security.py tests/test_path_security_extra_paths.py
git commit -m "feat: add extra_allowed_paths to PathSecurityHook"
```

---

### Task 2: Extend FileSystemMiddleware with extra_allowed_paths

**Files:**
- Modify: `core/filesystem/middleware.py`
- Test: `tests/test_filesystem_extra_paths.py`

**Step 1: Write the failing test**

Create `tests/test_filesystem_extra_paths.py`:

```python
from pathlib import Path
import pytest
from core.filesystem.middleware import FileSystemMiddleware


def test_extra_allowed_path_validates(tmp_path: Path) -> None:
    workspace = tmp_path / "project"
    workspace.mkdir()
    extra = tmp_path / "thread_files"
    extra.mkdir()
    (extra / "test.txt").write_text("hello")

    mw = FileSystemMiddleware(workspace_root=workspace, extra_allowed_paths=[extra], verbose=False)
    is_valid, error, resolved = mw._validate_path(str(extra / "test.txt"), "read")
    assert is_valid, error


def test_without_extra_paths_blocks(tmp_path: Path) -> None:
    workspace = tmp_path / "project"
    workspace.mkdir()
    extra = tmp_path / "thread_files"
    extra.mkdir()

    mw = FileSystemMiddleware(workspace_root=workspace, verbose=False)
    is_valid, error, _ = mw._validate_path(str(extra / "test.txt"), "read")
    assert not is_valid
    assert "outside workspace" in error.lower()
```

**Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/test_filesystem_extra_paths.py -v`
Expected: FAIL — `FileSystemMiddleware.__init__() got an unexpected keyword argument 'extra_allowed_paths'`

**Step 3: Implement**

Edit `core/filesystem/middleware.py` — add parameter to `__init__` and update `_validate_path`:

In `__init__` (after line 63, add parameter):

```python
    def __init__(
        self,
        workspace_root: str | Path,
        *,
        max_file_size: int = 10 * 1024 * 1024,
        allowed_extensions: list[str] | None = None,
        hooks: list[Any] | None = None,
        enabled_tools: dict[str, bool] | None = None,
        operation_recorder: FileOperationRecorder | None = None,
        backend: FileSystemBackend | None = None,
        verbose: bool = True,
        extra_allowed_paths: list[Path | str] | None = None,
    ):
```

After `self.verbose = verbose` (line 95), add:

```python
        self.extra_allowed_paths: list[Path] = [
            Path(p) if backend and backend.is_remote else Path(p).resolve()
            for p in (extra_allowed_paths or [])
        ]
```

In `_validate_path` (replace lines 120-123):

```python
        try:
            resolved.relative_to(self.workspace_root)
        except ValueError:
            if not any(resolved.is_relative_to(p) for p in self.extra_allowed_paths):
                return False, f"Path outside workspace\n   Workspace: {self.workspace_root}\n   Attempted: {resolved}", None
```

**Step 4: Run test to verify it passes**

Run: `uv run python -m pytest tests/test_filesystem_extra_paths.py -v`
Expected: 2 passed

**Step 5: Commit**

```bash
git add core/filesystem/middleware.py tests/test_filesystem_extra_paths.py
git commit -m "feat: add extra_allowed_paths to FileSystemMiddleware"
```

---

### Task 3: Thread extra_allowed_paths through LeonAgent

**Files:**
- Modify: `agent.py` (3 locations: `__init__`, `_add_filesystem_middleware`, `_add_command_middleware`)

**Step 1: Add parameter to LeonAgent.__init__**

After `verbose: bool = False,` (line 106), add:

```python
        extra_allowed_paths: list[Path | str] | None = None,
```

After `self._registry = registry` (line 128), add:

```python
        self.extra_allowed_paths: list[Path] = [Path(p).resolve() for p in (extra_allowed_paths or [])]
```

**Step 2: Pass to FileSystemMiddleware**

In `_add_filesystem_middleware` (line 866-877), add `extra_allowed_paths`:

```python
        middleware.append(
            FileSystemMiddleware(
                workspace_root=self.workspace_root,
                max_file_size=max_file_size,
                allowed_extensions=self.allowed_file_extensions,
                hooks=file_hooks,
                enabled_tools=fs_tools,
                operation_recorder=get_recorder(),
                backend=fs_backend,
                verbose=self.verbose,
                extra_allowed_paths=self.extra_allowed_paths,
            )
        )
```

**Step 3: Pass to PathSecurityHook**

In `_add_command_middleware` (line 933), change:

```python
            command_hooks.append(PathSecurityHook(workspace_root=self.workspace_root))
```

to:

```python
            command_hooks.append(PathSecurityHook(workspace_root=self.workspace_root, extra_allowed_paths=self.extra_allowed_paths))
```

**Step 4: Run existing tests to verify nothing breaks**

Run: `uv run python -m pytest tests/test_file_channel_service.py tests/test_storage_runtime_wiring.py -v`
Expected: all pass (no regression)

**Step 5: Commit**

```bash
git add agent.py
git commit -m "feat: thread extra_allowed_paths through LeonAgent to middleware"
```

---

### Task 4: Auto-inject thread files dir for local provider

**Files:**
- Modify: `backend/web/services/agent_pool.py`

**Step 1: Update create_agent_sync to accept extra_allowed_paths**

Change signature (line 20):

```python
def create_agent_sync(sandbox_name: str, workspace_root: Path | None = None, model_name: str | None = None, agent: str | None = None, queue_manager: Any = None, registry: Any = None, extra_allowed_paths: list[str] | None = None) -> Any:
```

In the `create_leon_agent` call (line 29-38), add:

```python
        extra_allowed_paths=extra_allowed_paths,
```

**Step 2: Inject thread files dir for local provider**

Replace the mount block (lines 94-107) with:

```python
    # @@@per-thread-file-access - ensure thread files are accessible
    from backend.web.services.workspace_service import ensure_thread_files

    workspace_id = thread_config.workspace_id if thread_config else None
    channel = ensure_thread_files(thread_id, workspace_id=workspace_id)

    if sandbox_type == "local":
        # Local: add thread files dir to agent's allowed paths
        agent_obj.extra_allowed_paths = [Path(channel["files_path"]).resolve()]
        # Rebuild middleware with updated paths
        # (agent already created, so we update the middleware directly)
```

Wait — the agent is already constructed by `create_agent_sync`. We need to pass `extra_allowed_paths` BEFORE construction. Restructure:

Before the `create_agent_sync` call (around line 82-85), compute extra_allowed_paths:

```python
    # @@@per-thread-file-access - ensure thread files are accessible from agent
    from backend.web.services.workspace_service import ensure_thread_files

    workspace_id = thread_config.workspace_id if thread_config else None
    channel = ensure_thread_files(thread_id, workspace_id=workspace_id)
    extra_allowed_paths = [channel["files_path"]] if sandbox_type == "local" else None

    agent_obj = await asyncio.to_thread(create_agent_sync, sandbox_type, workspace_root, model_name, agent_name, qm, registry, extra_allowed_paths)
```

Keep the existing remote mount block (lines 94-107), but update the condition since `ensure_thread_files` is already called above:

```python
    # @@@per-thread-bind-mounts - mount or copy thread files directory into sandbox
    if hasattr(agent_obj, "_sandbox") and sandbox_type != "local":
        from sandbox.config import MountSpec

        capability = agent_obj._sandbox.manager.provider_capability
        mode = "mount" if capability.mount.supports_mount else "copy"
        target = getattr(agent_obj._sandbox.manager.provider, 'WORKSPACE_ROOT', '/workspace') + '/files'
        mount = MountSpec(source=channel["files_path"], target=target, mode=mode, read_only=False)
        manager = getattr(agent_obj._sandbox, "_manager", None) or getattr(agent_obj._sandbox, "manager", None)
        if manager and hasattr(manager, "set_thread_bind_mounts"):
            manager.set_thread_bind_mounts(thread_id, [mount])
```

**Step 3: Commit**

```bash
git add backend/web/services/agent_pool.py
git commit -m "feat: auto-inject thread files dir as allowed path for local provider"
```

---

### Task 5: Add allowed_paths to SandboxConfig

**Files:**
- Modify: `sandbox/config.py`
- Modify: `backend/web/services/agent_pool.py` (merge config allowed_paths with auto-injected paths)

**Step 1: Add field to SandboxConfig**

In `SandboxConfig` class (after `init_commands` field, line 76):

```python
    allowed_paths: list[str] = Field(default_factory=list)
```

In `save()` method (after `init_commands` block, line 98-99):

```python
        if self.allowed_paths:
            data["allowed_paths"] = self.allowed_paths
```

**Step 2: Load and merge in agent_pool**

In `get_or_create_agent`, after computing `extra_allowed_paths` for local (from Task 4), also load config paths:

```python
    # Merge config-level allowed_paths
    from sandbox.config import SandboxConfig
    try:
        sandbox_config = SandboxConfig.load(sandbox_type)
        if sandbox_config.allowed_paths:
            config_paths = extra_allowed_paths or []
            config_paths.extend(sandbox_config.allowed_paths)
            extra_allowed_paths = config_paths
    except FileNotFoundError:
        pass  # local provider has no config file
```

**Step 3: Commit**

```bash
git add sandbox/config.py backend/web/services/agent_pool.py
git commit -m "feat: add configurable allowed_paths to SandboxConfig"
```

---

### Task 6: E2E verification — re-run local provider test

**Step 1: Re-run the e2e test from the earlier plan**

Start backend if not running. Then:

```bash
# Create local thread
TID=$(curl -sf -X POST http://127.0.0.1:8003/api/threads \
  -H 'Content-Type: application/json' \
  -d '{"sandbox": "local"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['thread_id'])")

# Upload canary
echo -n "leon-e2e-canary-12345" > /tmp/e2e-canary.txt
curl -sf -X POST "http://127.0.0.1:8003/api/threads/${TID}/workspace/upload?path=test.txt" \
  -F "file=@/tmp/e2e-canary.txt;filename=test.txt"

# Get the absolute path from upload response, use in prompt
ABS=$(curl -sf -X POST "http://127.0.0.1:8003/api/threads/${TID}/workspace/upload?path=test2.txt" \
  -F "file=@/tmp/e2e-canary.txt;filename=test2.txt" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['absolute_path'])")

# Start run with absolute path
curl -sf -X POST "http://127.0.0.1:8003/api/threads/${TID}/runs" \
  -H 'Content-Type: application/json' \
  -d "{\"message\": \"Read the file at ${ABS} and tell me its exact content.\"}"

# Consume SSE — expect PASS (canary in response)
```

Expected: `read_file` succeeds (no "Path outside workspace" error), agent returns canary string.

**Step 2: Cleanup**

```bash
curl -sf -X DELETE "http://127.0.0.1:8003/api/threads/${TID}"
rm /tmp/e2e-canary.txt
```
