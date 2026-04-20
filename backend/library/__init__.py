"""Library domain — file-backed + DB-backed asset library.

TENTATIVE DOMAIN. Target architecture §5.5 marks library as deferred;
boundaries may shift once an audit decides whether this is a real
standalone domain or a chat-side projection. This package is a temporary
home to get library code out of backend/web/services/ without settling
the domain question.

IN:
    - paths.py (LIBRARY_DIR)
    - service.py (library CRUD over files and recipe repo)
    - marketplace_client.py (HTTP client for Mycel Hub)

OUT:
    - Sandbox recipe definitions (sandbox/recipes.py)
    - Agent user registration (backend/identity/ + backend/threads/)
    - Snapshot installation (backend/agent_marketplace/snapshot_install.py)

Dependencies:
    top-level: sandbox/, storage/, config/
    backend:   identity/, sandboxes/, agent_marketplace/

See program/doc/core/backend-package-dependencies-2026-04-20.md §5.6.
"""
