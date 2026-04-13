# Database Refactor 02D Chat Schema Read-Model Adapter Proof

Date: 2026-04-14

Checkpoint:

- `database-refactor-02d-chat-schema-read-model-adapter`

Scope:

- runtime adapter correction for Supabase `staging`
- no DDL
- no legacy `chat_entities` / `chat_messages` recreation
- no fallback table probing
- no frontend work
- no LLM delivery work
- no PostgREST, RLS, grant, or service-role boundary change

## Contract

Live `staging` chat storage uses:

- `staging.chats`
- `staging.chat_members`
- `staging.messages`
- `staging.increment_chat_message_seq(p_chat_id text) -> bigint`

Runtime mapping:

- `ChatRow.type` maps to `staging.chats.type`.
- `ChatRow.created_by_user_id` maps to `staging.chats.created_by_user_id`.
- `ChatEntityRow` is backed by `staging.chat_members`.
- `ChatMessageRow.sender_id` maps to `staging.messages.sender_user_id`.
- `ChatMessageRow.mentioned_ids` maps to `staging.messages.mentions_json`.
- unread and mention state uses `staging.chat_members.last_read_seq`, not timestamp watermarks.

The `public` runtime mapping remains on the legacy tables so this staging slice does not widen into public compatibility migration:

- `public.chat_entities`
- `public.chat_messages`

## Source / Test Evidence

Regression tests:

```text
uv run pytest tests/test_supabase_chat_repo_schema.py::test_chat_repos_keep_public_legacy_tables -q
```

Red result before implementation:

```text
FAILED tests/test_supabase_chat_repo_schema.py::test_chat_repos_keep_public_legacy_tables
AssertionError: assert [] == ['chat_1']
```

Green result after implementation:

```text
1 passed
```

Focused package verification:

```text
uv run pytest tests/test_chat_service_schema_contract.py tests/test_supabase_chat_repo_schema.py -q
```

Result:

```text
7 passed
```

Wider schema routing regression pack:

```text
uv run pytest tests/test_chat_service_schema_contract.py tests/test_supabase_chat_repo_schema.py tests/test_supabase_thread_launch_pref_repo_schema.py tests/test_supabase_entity_repo_schema.py tests/test_lifespan_supabase_wiring.py tests/test_supabase_tool_task_repo_schema.py tests/test_supabase_thread_repo_schema.py tests/test_supabase_factory.py tests/test_threads_router_agent_schema_contract.py tests/test_supabase_member_repo_schema.py -q
```

Result:

```text
29 passed
```

## Backend API YATU

Fresh backend was running on validation port `18010` with:

- `LEON_STORAGE_STRATEGY=supabase`
- `LEON_DB_SCHEMA=staging`
- public Supabase REST/auth target
- private Postgres/Supavisor via existing ops startup script

Known non-blocking startup notes:

- local provider was available
- Daytona/AgentBay SDK imports still failed because optional SDK packages are not installed in this venv
- the proof did not rely on those providers

Temporary fixture:

- one temporary Supabase auth human
- one temporary `staging.users` human row
- one temporary `staging.users` agent row owned by that human
- one temporary local-provider main thread created through `POST /api/threads`
- one temporary direct chat
- one temporary message sent by the agent to the human with a human mention

Secrets, bearer tokens, and temporary password were not recorded.

API sequence and observed result:

```text
02D backend API YATU rerun start
POST /api/auth/login 200
POST /api/threads 200
POST /api/chats 200
POST /api/chats/{chat_id}/messages 200
GET /api/chats/{chat_id} 200
GET /api/chats/{chat_id}/messages 200
GET /api/chats before read 200
POST /api/chats/{chat_id}/read 200
GET /api/chats after read 200
02D backend API YATU RERUN PASS
```

Verified product behavior:

- `POST /api/chats` creates a chat against `staging.chats`.
- `POST /api/chats/{chat_id}/messages` writes to `staging.messages` through the sequence RPC.
- `GET /api/chats/{chat_id}` derives both human and agent participants from `staging.users`.
- `GET /api/chats/{chat_id}/messages` derives `sender_name` from `staging.users`.
- `GET /api/chats` before read returns the created chat with `unread_count = 1`.
- `GET /api/chats` before read returns `has_mention = true`.
- `POST /api/chats/{chat_id}/read` updates `chat_members.last_read_seq` to the latest message sequence.
- `GET /api/chats` after read returns `unread_count = 0`.
- `GET /api/chats` after read returns `has_mention = false`.

Cleanup completed / attempted:

- deleted temporary `staging.messages` rows by chat id
- deleted temporary `staging.chat_members` rows by chat id
- deleted temporary `staging.chats` row
- deleted temporary `agent.threads` row
- deleted temporary `staging.thread_launch_prefs` rows for the owner
- deleted temporary `staging.users` agent row
- deleted temporary `staging.users` human row
- deleted temporary Supabase auth user

## Stopline

02D closes the chat schema adapter mismatch exposed by 02C. It does not claim the whole chat product is complete.

Remaining separate concerns must stay as separate checkpoints:

- chat UX polish
- chat contact/sidebar cleanup
- token accounting
- model ownership/defaulting semantics
- full database ontology rewrite beyond current `staging` runtime adapter
