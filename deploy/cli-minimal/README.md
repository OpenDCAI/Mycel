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

## Network Shape

Default startup is local-only:

```bash
python3 deploy/cli-minimal/generate-env.py > deploy/cli-minimal/.env
docker compose --env-file deploy/cli-minimal/.env -f deploy/cli-minimal/compose.yml up
```

That publishes `mycel-backend` on `127.0.0.1:8042`. This is the safe default
for a single laptop.

To let `cel` on another machine connect to this CLI-minimal backend, publish an
explicit reachable URL:

```bash
python3 deploy/cli-minimal/generate-env.py \
  --bind-host 0.0.0.0 \
  --public-url http://<host-or-lan-ip>:8042 \
  > deploy/cli-minimal/.env
docker compose --env-file deploy/cli-minimal/.env -f deploy/cli-minimal/compose.yml up
```

Other machines should configure `cel` with `MYCEL_PUBLIC_URL`. Future CLI
onboarding should accept that URL, probe backend version/capabilities, and fail
loudly if the target is not a compatible Mycel communication backend.

`SUPABASE_ANON_KEY` and `LEON_SUPABASE_SERVICE_ROLE_KEY` are PostgREST JWTs
signed by `SUPABASE_JWT_SECRET`; do not replace them with opaque random strings.
