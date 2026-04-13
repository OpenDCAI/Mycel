# Database Refactor 02A PostgREST Exposure Runbook

Status: runbook only. Do not execute without Ledger authorization.

## Current Proof

Remote Supabase self-host config on ZGCA currently exposes:

```text
PGRST_DB_SCHEMAS=public,storage,graphql_public,staging
```

`agent` is not exposed today.

Source:

- server path: `/opt/supabase/repo/docker/.env`
- container: `supabase-rest`
- compose key: `PGRST_DB_SCHEMAS`

Supabase-py confirms `client.schema("agent")` requires the schema to be in Supabase's exposed schema list.

## Required Config Change

After the DB migration creates `agent.threads` and `agent.thread_tasks`, update the self-hosted Supabase docker env:

```dotenv
PGRST_DB_SCHEMAS=public,storage,graphql_public,staging,agent
```

Then restart or recreate only the PostgREST container from `/opt/supabase/repo/docker`:

```bash
cd /opt/supabase/repo/docker
docker compose up -d rest
```

If the env is already updated and only the schema cache needs reload, use:

```sql
NOTIFY pgrst, 'reload schema';
```

For this first `agent` exposure, prefer the container restart because the exposed schema list itself changes.

## Required Grants

The 02A migration grants only backend service-role access:

```sql
GRANT USAGE ON SCHEMA agent TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON agent.threads TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON agent.thread_tasks TO service_role;
```

Do not grant `anon` or `authenticated` in 02A. Direct frontend/PostgREST access, RLS, and realtime require a separate proof checkpoint.

## Post-Migration REST Proof

After migration and PostgREST exposure, prove service-role REST visibility from the app environment:

```python
from backend.web.core.supabase_factory import create_supabase_client

client = create_supabase_client()
threads = client.schema("agent").table("threads").select("id").limit(1).execute()
tasks = client.schema("agent").table("thread_tasks").select("thread_id,task_id").limit(1).execute()
print(len(threads.data), len(tasks.data))
```

Expected:

- no `PGRST106` / schema-not-exposed error
- no permission error
- `threads.data` is a list
- `tasks.data` is a list

Only after this proof should runtime repos route to `agent.*`.
