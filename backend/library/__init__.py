"""Library domain — product-side asset/template/skill library.

IN:
    - paths.py (LIBRARY_DIR)
    - service.py (library CRUD over files and recipe repo)

OUT:
    - Mycel-Hub integration (backend/hub/)
    - Sandbox recipe definitions (sandbox/recipes.py)
    - Agent user registration (backend/identity/ + backend/threads/)

Dependencies:
    top-level: sandbox/, storage/, config/
    backend:   identity/, sandboxes/

See program/doc/core/backend-package-dependencies-2026-04-20.md §5.6.
"""
