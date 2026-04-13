# Mycel Database Refactor Target Contract Matrix

Date: 2026-04-14

This document is the first Database Refactor PR artifact. It intentionally does
not apply DDL yet. Its job is to turn the external design reply, the
`mycel-db-design` repo, current Mycel storage code, and live Supabase metadata
into an executable migration plan.

## Sources

- GitHub issue reply: <https://github.com/nmhjklnm/mycel-db-design/issues/1#issuecomment-4237192274>
- Design repo checkout: `/Users/lexicalmathical/Codebase/mycel-db-design`
- Design commit: `9422bd8` (`refactor(container): remove terminal layer and volumes abstraction`)
- Mycel worktree: `/Users/lexicalmathical/worktrees/leonai--database-refactor`
- Live DB metadata source: Supabase Postgres using `LEON_POSTGRES_URL` from the currently running local backend process

## Current Live DB Facts

Command shape, with secrets supplied by operator runtime:

```bash
LEON_POSTGRES_URL='<from running backend env or ops docs>' uv run python - <<'PY'
import os
import psycopg

with psycopg.connect(os.environ["LEON_POSTGRES_URL"], connect_timeout=10) as conn:
    with conn.cursor() as cur:
        cur.execute("""
            select table_schema, table_name
            from information_schema.tables
            where table_schema in (
                'public','staging','identity','chat','agent',
                'container','hub','observability','eval'
            )
              and table_type = 'BASE TABLE'
            order by table_schema, table_name
        """)
        for schema, table in cur.fetchall():
            print(f"{schema}.{table}")
PY
```

Observed on 2026-04-14:

- Existing product schemas: `public`, `staging`
- Target domain schemas present: none of `identity`, `chat`, `agent`, `container`, `hub`, `observability`, `eval`
- Base table count across `public` + `staging`: `101`
- RLS policies in these schemas: `0`
- Functions in these schemas: `6`
- Realtime publication tables: `5`

Current functions:

```text
public.count_unread_per_chat
public.increment_member_thread_seq
public.next_mycel_id
staging.increment_chat_message_seq
staging.increment_user_thread_seq
staging.next_mycel_id
```

Current realtime publication:

```text
public.chat_members
public.message_reads
public.messages
public.relationships
public.threads
```

## Upstream Design Inconsistencies To Resolve Locally

The issue reply is newer than parts of the design files and should be treated
as the current human decision where it conflicts with the checked-out design
repo.

| Topic | Issue reply says | `mycel-db-design@9422bd8` actually says | Mycel PR ruling |
|---|---|---|---|
| Thread tasks | `tool_tasks` -> `thread_tasks` | `agent-schema.md` still defines `agent.tool_tasks` and realtime for `agent.tool_tasks` | Use `thread_tasks` as the Mycel target name; flag upstream design doc as stale |
| Chat deliveries/reactions/pins | Keep as future extension only | `chat-schema.md`, `overview.md`, and `schema-decisions.md` still define them as base chat tables | Exclude from P0 Database Refactor; do not migrate/create them now |
| Observability | Added `observability` schema | No `observability-schema.md` exists in commit `9422bd8`; eval tables are only discussed in the issue | Create an observability/eval target slice, but require a local Mycel schema contract before DDL |

## Target Classification

Classification meanings:

- `keep`: target concept already matches and can be carried forward.
- `rename`: same concept, better target name.
- `migrate`: move data/code from current schema/table into target domain table.
- `defer`: valid concept, but not in the first DDL slice.
- `delete candidate`: legacy product table should not get a target home.
- `route-out`: do not model as durable remote DB table; use runtime memory, provider API, Supabase Storage, or local runtime state.

### Identity

| Target | Current sources | Classification | Notes |
|---|---|---|---|
| `identity.users` | `staging.users`, `public.members`, `staging.agent_registry` | migrate | Human + agent unified actor table is the target. `members` and `agent_registry` should be migration sources only, not target concepts. |
| `identity.accounts` | `public.accounts`, `staging.accounts` | migrate | Login credentials stay in identity. Need one canonical account source during migration. |
| `identity.assets` | `staging.assets`; avatar repair code writes assets | migrate | Static user-managed assets belong here. Agent artifacts do not. |
| `identity.user_settings` | `public.user_settings`, `staging.user_settings` | migrate | Convert toward scoped KV settings. Model/token config must not stay as opaque accidental blob forever. |
| `identity.invite_codes` | `public.invite_codes`, `staging.invite_codes` | migrate | Registration control belongs to identity. |
| `identity.model_providers` | `user_settings.models_config`, runtime model config | defer | Valid direction, but issue reply marks model/token as outside current design handling. Needs runtime contract audit first. |
| `identity.model_mappings` | `user_settings.default_model`, `agent_configs.model` | defer | Same as above. Must settle caller-vs-owner-vs-agent model lookup semantics before DDL. |

Current code surfaces:

- `storage/providers/supabase/member_repo.py`
- `storage/providers/supabase/user_settings_repo.py`
- `storage/providers/supabase/invite_code_repo.py`
- `backend/web/services/auth_service.py`

### Chat

| Target | Current sources | Classification | Notes |
|---|---|---|---|
| `chat.chats` | `public.chats`, `staging.chats` | migrate | Keep target seq/preview/list behavior, but validate current frontend expectations first. |
| `chat.messages` | `public.messages`, `staging.messages`; SQLite `chat_messages` | migrate | Message order should use `messages.seq`. |
| `chat.chat_members` | `public.chat_members`, `staging.chat_members` | migrate | Unread source of truth is `chat_members.last_read_seq`. |
| `chat.contacts` | `public.contacts`, `staging.contacts` | migrate | Need preserve contact state semantics. |
| `chat.relationships` | `public.relationships`, `staging.relationships` | migrate | Must include initiator semantics if absent in current code/data. |
| `chat.message_attachments` | current attachment/files behavior | defer | Add only when file/message attachment path is contract-ready. |
| `chat.message_deliveries` | `public.message_deliveries` | delete candidate / defer | Not part of base chat schema per issue reply. Current delivery resolver is routing strategy, not per-device delivery state. |
| `chat.message_reactions` | none | defer | Future extension only. If quality feedback is needed, route to observability/feedback, not base chat. |
| `chat.message_pins` | none | defer | Future extension only. Conversation pinning is not message pinning. |
| `message_reads` | `public.message_reads` | delete candidate | Not target unread model. |
| `chat_sessions` | `public.chat_sessions`, `staging.chat_sessions` | route-out | Removed from target. Runtime/session state should not be base chat DB. |

Current code surfaces:

- `storage/providers/supabase/chat_repo.py`
- `storage/providers/supabase/contact_repo.py`
- `storage/providers/supabase/chat_session_repo.py`
- `backend/web/routers/conversations.py`
- `backend/web/routers/threads.py`

### Agent

| Target | Current sources | Classification | Notes |
|---|---|---|---|
| `agent.agent_configs` | `public.agent_configs`, `staging.agent_configs` | migrate | Agent behavior definition belongs here. |
| `agent.agent_rules` | `public.agent_rules`, `staging.agent_rules` | migrate | Keep separate CRUD object. |
| `agent.agent_skills` | `public.agent_skills`, `staging.agent_skills` | migrate | Keep separate CRUD object. |
| `agent.agent_sub_agents` | `public.agent_sub_agents`, `staging.agent_sub_agents` | migrate | Config-time sub-agent definitions. |
| `agent.threads` | `public.threads`, `staging.threads`, `staging.thread_config` | migrate | Thread runtime must eventually point at container workspace, not terminal. |
| `agent.thread_launch_prefs` | `public.thread_launch_prefs`, `staging.thread_launch_prefs` | migrate | Preserve if still product-visible launch preference. |
| `agent.run_events` | `public.run_events`, `staging.run_events` | migrate | Runtime/event history belongs with agent execution. |
| `agent.summaries` | `public.summaries`, `staging.summaries` | migrate | Keep if used by context compaction/summaries. |
| `agent.message_queue` | `public.message_queue`, `staging.message_queue` | migrate | Queue is agent runtime infra. |
| `agent.file_operations` | `public.file_operations`, `staging.file_operations` | migrate | File/sync default follows design; `sync_files` is not target. |
| `agent.thread_tasks` | `public.tool_tasks`, `staging.agent_thread_tasks`, SQLite `tasks` | rename + migrate | Use `thread_tasks`, not `tool_tasks`. `agent_thread_tasks` is closer but still transitional. |
| `agent.schedules` | `public.cron_jobs`, `staging.cron_jobs` | rename + migrate | Old `cron_jobs` should not survive. |
| `agent.schedule_runs` | none or implicit run/events | migrate/add | Required for schedule-level observability; `run_events` does not replace it. |
| LangGraph checkpoint tables | `public.checkpoints`, `public.checkpoint_*`, `staging.checkpoint_*`, `staging.writes` | migrate | Keep exact LangGraph structure; schema move should not alter framework contract. |
| `agent_registry` | `public.agent_registry`, `staging.agent_registry`, SQLite `agents` | delete candidate | Replaced by unified identity + agent configs. |
| `panel_tasks` | `public.panel_tasks`, SQLite `panel_tasks` | delete candidate | Do not give a new product target table. |

Current code surfaces:

- `storage/providers/supabase/tool_task_repo.py`
- `storage/providers/supabase/cron_job_repo.py`
- `storage/providers/supabase/agent_registry_repo.py`
- `storage/providers/supabase/panel_task_repo.py`
- `storage/providers/supabase/thread_repo.py`
- `backend/web/services/cron_service.py`
- `backend/web/services/task_service.py`

### Container / Runtime

| Target | Current sources | Classification | Notes |
|---|---|---|---|
| `container.devices` | sandbox provider/account resource config; no exact current table | migrate/add | Device is persistent compute endpoint. Need daemon/provider reality check before DDL. |
| `container.sandbox_templates` | `public.library_recipes`, `staging.library_recipes`, SQLite `library_recipes` | rename + migrate | The issue reply says `sandbox_templates`, not `sandbox_recipes`. This supersedes earlier discussion naming. |
| `container.sandboxes` | `public.sandbox_leases`, `public.sandbox_instances`, staging equivalents | migrate | Target combines persistent sandbox desired/observed state. |
| `container.workspaces` | `sandbox_leases`, thread terminal/lease binding, file workspace paths | migrate | Must replace thread -> terminal -> lease assumptions with thread -> workspace. |
| `container.resource_snapshots` | `lease_resource_snapshots` | migrate | Target commit reply says resource snapshots remain in container. |
| `container.provider_events` | `public.provider_events`, `staging.provider_events` | migrate | Issue reply places provider events in container; observability boundary should be revisited later. |
| terminals | `abstract_terminals`, `thread_terminal_pointers`, `terminal_commands`, `terminal_command_chunks` | route-out | Issue reply: terminal is stateless sandbox exec API, no PTY persistence. Current Mycel code still depends heavily on terminal repos, so this is a major implementation slice. |
| volumes | `sandbox_volumes` | route-out | Issue reply: file upload/download uses Supabase Storage directly; volumes abstraction is invalid. |
| `sync_files` | `public.sync_files`, `staging.sync_files`, SQLite `sync_files` | route-out/delete candidate | No target model unless a future sync feature is explicitly designed. |

Current code surfaces:

- `storage/providers/supabase/lease_repo.py`
- `storage/providers/supabase/terminal_repo.py`
- `storage/providers/supabase/chat_session_repo.py`
- `storage/providers/supabase/sandbox_volume_repo.py`
- `storage/providers/supabase/sync_file_repo.py`
- `storage/providers/supabase/resource_snapshot_repo.py`
- `storage/providers/supabase/provider_event_repo.py`
- `backend/web/services/file_channel_service.py`
- `backend/web/services/thread_state_service.py`
- `backend/web/routers/threads.py`
- `sandbox/lease.py`
- `sandbox/terminal.py`

### Hub / Marketplace

| Target | Current sources | Classification | Notes |
|---|---|---|---|
| `hub.marketplace_publishers` | `public.marketplace_publishers`, `staging.marketplace_publishers` | migrate | Use `public.marketplace_*` as source because it has real data; staging is empty per issue. |
| `hub.marketplace_items` | `public.marketplace_items`, `staging.marketplace_items` | migrate | Same source rule. |
| `hub.marketplace_versions` | `public.marketplace_versions`, `staging.marketplace_versions` | migrate | Same source rule. |

Current code surfaces:

- `backend/web/models/marketplace.py`
- `backend/web/routers/marketplace.py`
- `frontend/app/src/pages/MarketplacePage.tsx`

### Observability / Eval

| Target | Current sources | Classification | Notes |
|---|---|---|---|
| `observability.eval_runs` or `eval.eval_runs` | `public.eval_runs`, `staging.eval_runs`, `eval/repo.py` | migrate | Required for Mycel agents developing Mycel. Need local schema contract because upstream commit has no observability DDL file. |
| `observability.eval_metrics` | `public.eval_metrics`, `staging.eval_metrics` | migrate | Keep. |
| `observability.eval_llm_calls` | `public.eval_llm_calls`, `staging.eval_llm_calls` | migrate | Keep. |
| `observability.eval_tool_calls` | `public.eval_tool_calls`, `staging.eval_tool_calls` | migrate | Keep. |
| `observability.evaluation_batches` | `public.evaluation_batches`, `staging.evaluation_batches` | migrate | Keep if current eval harness uses batches. |
| `observability.evaluation_batch_runs` | `public.evaluation_batch_runs`, `staging.evaluation_batch_runs` | migrate | Keep if current eval harness uses batches. |
| `provider_events` | `public.provider_events`, `staging.provider_events` | split decision needed | Issue body suggested eval/observability; issue reply says container retains provider_events. Treat as container P0, maybe mirror/aggregate later. |
| `audit_logs` | `public.audit_logs` | delete candidate | Not current core product schema. |

Current code surfaces:

- `eval/repo.py`
- `storage/providers/supabase/eval_repo.py`
- `storage/providers/supabase/provider_event_repo.py`
- `backend/web/routers/webhooks.py`

## Proposed PR Shape

This PR should start as a major Database Refactor branch, but not as a single
blind DDL dump. The safe sequence is:

1. `database-refactor-00-target-contract-and-migration-slicing`
   - Land this matrix.
   - Get Ledger acceptance on the first implementation slice.
2. `database-refactor-01-schema-loader-and-search-path`
   - Introduce an explicit schema-addressing layer for Supabase repos so table
     access is not hard-coded to whatever `LEON_DB_SCHEMA` points at.
   - No product table rename yet.
3. `database-refactor-02-thread-tasks-schedules`
   - Rename `tool_tasks` / `agent_thread_tasks` concept to `agent.thread_tasks`.
   - Rename `cron_jobs` concept to `agent.schedules`.
   - Add `agent.schedule_runs`.
4. `database-refactor-03-terminal-volume-route-out`
   - Remove durable terminal/command/chunk pointer assumptions from the runtime
     path.
   - Replace thread -> terminal -> lease file path lookup with thread ->
     workspace / sandbox exec API contract.
5. Later slices:
   - identity migration
   - chat migration
   - container sandbox/workspace migration
   - hub marketplace migration
   - observability schema

## Stopline

Do not write destructive migrations or drop legacy tables until:

- target table inventory is accepted by Ledger;
- source table row counts and owner/key relationships are captured;
- each slice has a rollback or route-out story;
- backend API YATU exists for the affected product path;
- frontend Playwright CLI YATU exists for affected UI paths;
- public/staging compatibility shims are not added as a new permanent layer.
