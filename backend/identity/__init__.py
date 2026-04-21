"""Identity domain — users, auth, ownership, avatar, profile.

Aggregate roots: `user`, `auth_session`.

IN:
    - auth/ {service, dependencies, user_resolution, runtime_bootstrap,
             supabase_runtime}
    - avatar/ {files, paths, urls} — urls.py is the canonical
      implementation of messaging.avatars.AvatarUrlBuilder
    - profile.py
    - contact_bootstrap.py (owner<->agent initial contact edge)

OUT:
    - Chat relationships (messaging/)
    - Thread ownership records (backend/threads/; we only provide user_id)
    - Sandbox ownership (backend/sandboxes/)
    - Agent instance id persistence (core/identity/agent_registry.py;
      that handles agent_id, we handle user_id)

Canonical protocols implemented:
    - messaging.avatars.AvatarUrlBuilder (via avatar/urls.py)

Dependencies:
    top-level: storage/, messaging/, config/, protocols/
    backend:   none (leaf domain among backend/)

See program/doc/core/backend-package-dependencies-2026-04-20.md §5.2.
"""
