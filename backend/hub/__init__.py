"""Mycel-Hub integration boundary.

IN:
    - client.py (HTTP client for Mycel Hub)
    - snapshot_install.py (install agent snapshots from Mycel Hub)
    - versioning.py (semver bumper used by Hub publish/upgrade flows)

OUT:
    - Product-side library ownership (backend/library/)
    - HTTP surface (backend/web/routers/marketplace.py)
    - Agent user CRUD ownership (backend/threads/agent_user_service.py)

Dependencies:
    top-level: storage/, config/
    backend:   identity/, threads/

See program/doc/core/backend-package-dependencies-2026-04-20.md §5.7.
"""
