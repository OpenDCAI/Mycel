# Mycel CLI-Minimal Deploy

This compose profile is the local communication backend for CLI-first users.
It is not the full Mycel platform and it is not a forked schema.

Long-running services:

- `postgres`: the only database.
- `postgrest`: Supabase-compatible REST storage surface.
- `gateway`: thin nginx route for `/rest/v1/*`.
- `mycel-backend`: Mycel business API with `MYCEL_RUNTIME_PROFILE=communication`.

One-shot service:

- `schema-init`: runs `scripts/apply_app_schema.py` against `storage/schema/app_schema.sql`
  and manifest patches, then exits.

The ordinary CLI install must not pull Docker images. This stack is only used
when a user explicitly asks for local communication service startup.

Full platform deployment belongs to operator runbooks, not this profile.
