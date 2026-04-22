"""Sandboxes domain — HTTP/service layer for sandbox lifecycle.

Aggregate root: `sandbox_runtime` (schema-side; owned via storage/ + sandbox/).
This package wraps the top-level sandbox/ provider abstraction with
app.state-aware caching, user-scoped views, and resource projections.

IN:
    - inventory.py (provider init cache)
    - paths.py (SANDBOXES_DIR)
    - provider_availability.py, provider_factory.py
    - recipe_catalog.py, recipe_bootstrap.py
    - local_workspace.py (LEON_LOCAL_WORKSPACE_ROOT)
    - runtime/ {metrics, mutations, reads}
    - thread_resources.py (destroy thread's sandbox resources)
    - user_reads.py (user-scoped sandbox aggregation)
    - service.py (HTTP-facing sandbox service)
    - account.py (user account resource limits)
    - resources/ {common, io, projection, provider_boundary,
                  provider_contracts, user_projection}

OUT:
    - Provider implementation details (sandbox/providers/)
    - Lease state machine (sandbox/lease.py, sandbox/lifecycle.py)
    - Volume engine (sandbox/volume.py)
    - Thread-sandbox binding (backend/threads/sandbox_resolution.py)

Dependencies:
    top-level: sandbox/, storage/, config/
    backend:   identity/, threads/ (reverse reads for projection)

See program/doc/core/backend-package-dependencies-2026-04-20.md §5.5.
"""
