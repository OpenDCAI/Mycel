"""Runtime bootstrap — shared process-level startup plumbing.

NOT A DOMAIN. This is the single approved cross-app utility bucket
(target architecture §5.6 "No utils/common/shared/helpers"). Exists
because multiple FastAPI app shells (backend/web/main.py and
backend/monitor_app/main.py) share startup plumbing; the alternative is
duplication.

IN:
    - app_entrypoint.py (uvicorn runner, CORS, env loading, port resolution)
    - request_app.py (get_app(request) FastAPI dep)
    - storage.py (build_runtime_storage_state; web + monitor_app share)
    - storage_container_cache.py (process-local StorageContainer cache)

OUT:
    - Domain logic (belongs in each domain)
    - Domain-aware state (this package is domain-agnostic)

Scope discipline: if code here starts knowing about specific domains,
refactor it into that domain's own bootstrap.py.

See program/doc/core/backend-package-dependencies-2026-04-20.md §5.10.
"""
