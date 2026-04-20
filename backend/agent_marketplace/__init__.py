"""Agent marketplace — snapshot installation + versioning.

TENTATIVE DOMAIN name. This package holds Mycel-Hub-side machinery that
didn't fit library/ directly. If a library audit concludes library and
marketplace should merge, this package dissolves back into library/.

IN:
    - snapshot_install.py (install agent snapshots from Mycel Hub)
    - versioning.py (semver bumper used by marketplace)

OUT:
    - HTTP surface (backend/web/routers/marketplace.py)
    - Hub API client (backend/library/marketplace_client.py)
    - Agent user DB writes (backend/threads/agent_user_service.py)

Dependencies:
    top-level: storage/, config/
    backend:   identity/, threads/ (agent_user_service)

See program/doc/core/backend-package-dependencies-2026-04-20.md §5.7.
"""
