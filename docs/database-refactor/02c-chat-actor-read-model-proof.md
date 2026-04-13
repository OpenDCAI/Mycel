# Database Refactor 02C Chat Actor Read-Model Proof

Date: 2026-04-14

Checkpoint:

- `database-refactor-02c-chat-actor-read-model-strict-proof`

Scope:

- proof-first backend API YATU
- no DDL
- no frontend work
- no fallback routing
- no RLS/grant/PostgREST exposure change
- no service-role boundary change
- no LLM delivery work

Goal:

- decide whether the 02B Supabase actor read-model is strict enough for chat participant and message-display surfaces

## Setup

Fresh backend was launched on validation port `18010` with the existing Supabase local runtime startup script.

Known non-blocking startup notes:

- local sandbox provider was available
- Daytona/AgentBay SDK imports still failed because optional SDK packages are not installed in this venv
- the proof did not rely on those providers

Temporary fixture:

- one temporary Supabase auth human
- one temporary `staging.users` human row
- one temporary `staging.users` agent row owned by that human
- one temporary main thread created through `POST /api/threads`

Secrets and temporary password were not recorded.

## Backend API YATU Result

API sequence:

```text
POST /api/auth/login
POST /api/threads
POST /api/chats
```

Observed result:

- `POST /api/auth/login`: 200
- `POST /api/threads`: 200
- created thread id: `agent_02c_w589u2gv-1`
- `POST /api/chats`: 500

The proof stopped at the first failing product API surface as required by the 02C stopline.

`POST /api/chats` response body:

```text
Internal Server Error
```

Backend traceback root:

```text
storage/providers/supabase/chat_repo.py:105
SupabaseChatEntityRepo.find_chat_between(...)
self._t().select("chat_id").eq("user_id", user_a).execute()

postgrest.exceptions.APIError:
{
  "message": "Could not find the table 'staging.chat_entities' in the schema cache",
  "code": "PGRST205",
  "hint": "Perhaps you meant the table 'staging.chat_sessions'",
  "details": null
}
```

## Cleanup

Cleanup completed for the fixture rows created before the failure:

- deleted temporary `agent.threads` row
- deleted temporary `staging.thread_launch_prefs` row
- deleted temporary `staging.users` agent row
- deleted temporary `staging.users` human row
- deleted temporary Supabase auth user

No chat row/message rows were created because `POST /api/chats` failed before insertion.

## Classification

This is not a narrow 02B actor read-model mismatch.

The first failing surface is the chat storage schema boundary:

- current `SupabaseChatEntityRepo` still targets `staging.chat_entities`
- live target schema does not expose `staging.chat_entities`
- canonical/current design direction is `chats / chat_members / messages`, not `chat_entities / chat_messages`

Therefore 02C cannot upgrade 02B to strict yet.

Recommended next checkpoint:

- a dedicated chat schema/read-model migration or adapter checkpoint
- likely target surfaces:
  - `SupabaseChatRepo`
  - `SupabaseChatEntityRepo`
  - `SupabaseChatMessageRepo`
  - `/api/chats`
  - `/api/chats/{chat_id}`
  - `/api/chats/{chat_id}/messages`
- expected DB contract should be decided before code:
  - `chat_members`, not legacy `chat_entities`
  - `messages`, not legacy `chat_messages`
  - unread should be based on `chat_members.last_read_seq` when this slice reaches unread/read proof

Stopline remains:

- do not recreate `chat_entities` just to satisfy old code
- do not add fallback table probing
- do not patch this inside 02C without a new Ledger ruling
