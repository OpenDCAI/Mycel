# Distributed Group Workflow YATU

## User Story

A user wants to prove that Mycel group workflow is a thin workflow layer over
chat, not a separate local collaboration system. A supervisor and worker may run
on different machines, but they still share one backend chat, workflow state,
task store, and message history.

## Entry Surfaces

- Real backend process from the current branch.
- Installed `cel` CLI or SDK against that backend.
- Public HTTP API through SDK/CLI, not in-process service calls.

Do not inspect storage directly as proof. Direct DB checks are allowed only as
debugging after the user-facing proof fails.

Group workflow commands manage workflow state. Agent-to-agent communication
must still happen through top-level `cel send-message` and `cel read-message`.

## Setup

1. Start the current-branch backend with the real schema, including
   `chat.workflow_state.state_version`.
2. Use a fresh `MYCEL_HOME`.
3. Create a guest owner or login as an owner.
4. Create at least two external identities.
5. Start local `cel self start` only where terminal/runtime wake is part of the
   test.

## User Loop

1. Create a group through `cel group create`.
2. Create at least one task through `cel group <group_id> task create <subject>`.
3. Send supervisor-to-worker and worker-to-supervisor messages through
   top-level `cel send-message`, not through a group-specific send helper.
4. Read messages through top-level `cel read-message`.
5. Delete one machine's local group file.
6. Confirm `cel group show`, `cel group <group_id> task list`, and
   `cel group <group_id> task show <task_id>` still reconstruct from backend
   workflow/task truth.
7. Run a stale workflow-write probe from two clients and confirm the backend
   rejects or resolves the race without silent overwrite.

## Pass Bar

- `group_id` is a backend chat id.
- Workflow config writes carry an explicit version when they depend on current
  backend state.
- Stale workflow writes produce HTTP 409 or a successful bounded retry that
  preserves both participants.
- Chat messages and read cursors remain regular chat behavior.
- Guest users can create external users but cannot access sandbox resources.
- Worker stop may forward the worker's real output as chat; worker silent/idle
  detection is a local health observation and must not create a chat message.
- No local-only schema, copied group JSON, or DB-side special case is required.

## Pitfalls

- A helper-level service test is not YATU.
- A local-only group file passing the test is not proof of distributed workflow.
- A separate group message channel fails the architecture even if the demo
  appears to work.
- A silent 422/409 swallowed by CLI output fails the card; errors must explain
  the backend contract mismatch.
