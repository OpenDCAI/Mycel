# Database Refactor 02E Thread Task Tool Surface Proof

Date: 2026-04-14

Checkpoint:

- `database-refactor-02e-thread-task-tool-surface-strict-proof`

Scope:

- `agent.thread_tasks` only
- proof-first validation through ToolRegistry / ToolRunner
- no DDL
- no schedule / cron work
- no panel task migration
- no background-run API change
- no route rename
- no frontend work
- no LLM delivery
- no fallback table probing
- no `public.tool_tasks` compatibility work
- no run-history table design

## Boundary

`agent.thread_tasks` is the Mycel thread-scoped task/checkpoint-style work list used by:

- `TaskCreate`
- `TaskList`
- `TaskGet`
- `TaskUpdate`

It is not:

- background bash/agent run history
- long-running tool execution progress
- `panel_tasks`
- schedules or `schedule_runs`
- the stale upstream `agent.tool_tasks` design

Important route note:

- `/api/threads/{thread_id}/tasks` is not a proof surface for this checkpoint.
- Current code uses that route for background bash/agent runs, not `agent.thread_tasks` records.

## RED / GREEN

Added a strict integration test that registers `TaskService` into `ToolRegistry`, calls task tools through `ToolRunner.wrap_tool_call()`, and verifies the write/read path reaches `agent.thread_tasks`.

RED command:

```text
uv run pytest tests/test_thread_task_tool_surface_schema.py -q
```

RED result:

```text
FAILED tests/test_thread_task_tool_surface_schema.py::test_task_tools_persist_to_agent_thread_tasks_through_tool_runner
<tool_use_error>FakeSupabaseQuery.select() got an unexpected keyword argument 'count'</tool_use_error>
```

This was the correct failure: the test reached `ToolRunner -> TaskService -> SupabaseToolTaskRepo.next_id`, and the fake Supabase test client did not support the `select(..., count="exact")` call shape used by the real repo.

Minimal implementation:

- allow the fake Supabase `select()` helper to accept keyword arguments used by supabase-py

GREEN result:

```text
uv run pytest tests/test_thread_task_tool_surface_schema.py -q
1 passed
```

## Live Supabase Proof

A live proof harness ran with:

- `LEON_STORAGE_STRATEGY=supabase`
- `LEON_DB_SCHEMA=staging`
- public Supabase REST target
- service-role storage client
- a temporary thread id

The proof used the real tool execution surface:

```text
ToolRegistry
TaskService
ToolRunner.wrap_tool_call
TaskCreate -> TaskList -> TaskGet -> TaskUpdate
SupabaseToolTaskRepo
agent.thread_tasks
```

Observed result:

```text
02E ToolRunner live Supabase proof start
TaskCreate created 1
agent.thread_tasks rows after create 1
TaskList total 1
TaskGet metadata checkpoint 02e
TaskUpdate status completed
02E ToolRunner live Supabase proof PASS
02E cleanup deleted rows 1
```

Secrets and service-role keys were not printed.

## Cleanup

The live proof deleted the temporary `agent.thread_tasks` row by its temporary thread id.

Observed cleanup:

```text
02E cleanup deleted rows 1
```

## Classification

Closure evidence is mechanism-layer, not backend API YATU.

Reason:

- there is no true product HTTP task-card API for `agent.thread_tasks` in the current code
- `/api/threads/{thread_id}/tasks` is a background-run API and is explicitly out of scope

This proof is still stronger than repo-only evidence because it exercises the real tool dispatch path through `ToolRegistry` and `ToolRunner`, not direct repository calls or private `TaskService` helper calls.

## Stopline

02E proves the current `agent.thread_tasks` tool surface is wired through the target domain table.

It does not claim:

- task UX is complete
- background run tasks are renamed or refactored
- schedules are migrated
- panel tasks are migrated
- tool run history is modeled
- PR #507 is ready to undraft or merge
