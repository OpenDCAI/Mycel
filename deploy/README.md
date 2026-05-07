# Mycel Deploy Profiles

This directory is not the whole production deployment system. It contains
repo-owned compose profiles that are useful as product contracts.

## Profiles

### `cli-minimal`

`deploy/cli-minimal` is the local communication backend for CLI-first users.
It runs the Mycel business API in `MYCEL_RUNTIME_PROFILE=communication` and
uses the formal app schema bootstrap path.

It is intentionally small:

- one PostgreSQL database
- one PostgREST service exposing the Supabase-style storage surface
- one thin nginx gateway for `/rest/v1/*`
- one Mycel backend process
- one `schema-init` one-shot service

It is not a forked schema and it is not the full Mycel platform.

### Full Platform

Full deployment is not currently represented as `deploy/full`. The current full
runtime path is the root `docker-compose.yml` plus operator-managed Supabase /
Coolify configuration. Promoting that into `deploy/full` needs a separate
architecture decision because it would become a public self-hosting contract.

Do not infer from this directory that CLI-minimal is the only supported Mycel
deployment shape.
