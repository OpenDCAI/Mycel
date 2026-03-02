# Sandbox Bug Report — 2026-03-06

Two independent bugs need fixing, both visible in the `feat/resource-page` worktree
(frontend at `localhost:5174`). Neither overlaps with PR #130 (file-transfer UX rewrite).

---

## Bug 1 — Daytona SDK/proxy routing mismatch → all sandbox file ops return 503

### Symptom

Every file read or write in a Daytona sandbox fails. The backend returns 503 for any
file operation (read, write, list). The agent silently can't write files to disk either.

### Root cause

`daytona-sdk` drifted to `0.149.0` while the server daemon on ZGCA is `v0.141.0`.
Between these versions, the toolbox proxy routing convention changed:

| Version | Routing format |
|---------|----------------|
| 0.139.0 (lockfile) | host-based: sandbox ID encoded in subdomain |
| 0.149.0 (installed) | path-based: `http://proxy.localhost:4000/toolbox/{sandbox_id}/toolbox/...` |

The server proxy (v0.141.0) still uses the old convention and returns:

```
HTTP 401 Unauthorized
"failed to parse request host: invalid host format: port and sandbox ID not found"
```

### Evidence

1. `uv.lock` pins `daytona-sdk==0.139.0` (uploaded 2026-02-03). This was the last
   known-working version.

2. Currently installed:
   ```
   $ uv pip show daytona-sdk
   Version: 0.149.0
   ```

3. The `ToolboxApiClientProxy` source confirms path-based routing in 0.149.0:
   ```python
   # .venv/lib/python3.12/site-packages/daytona_sdk/internal/toolbox_api_client_proxy.py
   def param_serialize(self, *args, **kwargs):
       resource_path = f"/{self._sandbox_id}{resource_path}"   # prepend sandbox ID to path
       kwargs["_host"] = self._toolbox_base_url                # = http://proxy.localhost:4000/toolbox
   ```
   Final URL sent: `http://proxy.localhost:4000/toolbox/{sandbox_id}/toolbox/files`

4. Direct curl confirms 401 from the proxy:
   ```bash
   $ curl "http://proxy.localhost:4000/toolbox/eeaa01b6-.../toolbox/files"
   {"message":"unauthorized: failed to parse request host: invalid host format: port and sandbox ID not found"}
   ```

5. The proxy IS reachable (SSH tunnel `localhost:4000 → ZGCA:4000` is active).
   The problem is purely the routing format mismatch.

### Affected files

- `pyproject.toml` — `daytona = ["daytona-sdk>=0.10.0", ...]` (overly loose pin)
- `uv.lock` — should be the source of truth, pinned to 0.139.0

### Fix

Restore the lockfile version. In the project root:

```bash
uv sync
```

This downgrades `daytona-sdk` from 0.149.0 → 0.139.0 (and matching
`daytona-api-client`, `daytona-toolbox-api-client`, etc.).

Then tighten the pin in `pyproject.toml` to prevent future drift:

```toml
# Before
daytona = ["daytona-sdk>=0.10.0", ...]

# After
daytona = ["daytona-sdk>=0.139.0,<0.140.0", ...]
```

Verify the fix by running a file write through the backend:

```bash
curl -X POST http://localhost:8002/api/threads/{thread_id}/sandbox/write \
  -H "Content-Type: application/json" \
  -d '{"path": "/home/daytona/test.txt", "content": "hello"}'
```

---

## Bug 2 — Local file browser crashes with `[Errno 1] Operation not permitted: '.Trash'`

### Symptom

Opening the file browser panel for a **local** session shows:

```
API 400: {"detail":"[Errno 1] Operation not permitted: '/Users/lexicalmathical/.Trash'"}
```

### Root cause

`LocalSessionProvider.list_dir()` calls `child.stat()` for every entry in the
directory. On macOS, `.Trash` (and a few other system dirs) requires Full Disk Access
permission. Without it, `stat()` raises `PermissionError`.

```python
# sandbox/providers/local.py  line ~147
for child in target.iterdir():
    item_type = "directory" if child.is_dir() else "file"
    size = child.stat().st_size if child.exists() else 0   # ← raises PermissionError on .Trash
    items.append({"name": child.name, "type": item_type, "size": int(size)})
```

The exception propagates as `RuntimeError("Failed to list directory: ...")` in
`resource_service.sandbox_browse()`, which the router converts to a 400 response.
The entire directory listing fails even though only one entry is inaccessible.

Note: `resource_service.sandbox_browse()` already filters out dot-files
(`name.startswith(".")`) — but the filter runs **after** `list_dir` returns, so it
never gets a chance to save the listing.

### Affected file

`sandbox/providers/local.py` — `LocalSessionProvider.list_dir()` around line 147.

### Fix

Wrap the `stat()` call in a try/except and skip inaccessible entries:

```python
def list_dir(self, session_id: str, path: str) -> list[dict]:
    target = Path(path)
    if not target.exists() or not target.is_dir():
        return []
    items: list[dict] = []
    for child in target.iterdir():
        try:
            item_type = "directory" if child.is_dir() else "file"
            size = child.stat().st_size if child.exists() else 0
        except PermissionError:
            continue  # skip system dirs this process can't access
        items.append({"name": child.name, "type": item_type, "size": int(size)})
    return items
```

Verify: start the local backend, open the file browser on the root (`/Users/lexicalmathical`),
confirm the listing renders without error and `.Trash` is simply absent from the list.

---

## Where to make the changes

Both bugs live in the **main codebase** (shared across worktrees via the git repo).
The `feat/resource-page` worktree (`~/worktrees/leonai--feat-resource-page`) is
where the resource page and local file browser UI live, so that's the appropriate
worktree to develop and test these fixes.

Suggested branch name: `fix/sandbox-toolbox-routing-and-local-permissions`
