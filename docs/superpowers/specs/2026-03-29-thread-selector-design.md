# Thread Selector Design

Date: 2026-03-29

## Goal

Replace raw `thread_id` text entry in scheduled tasks with a real thread selector, while keeping the implementation minimal and aligned with the current codebase.

The first version must:

- let scheduled tasks choose from the current user's own threads
- avoid introducing a new cross-user thread visibility model
- produce a reusable frontend picker and a reusable backend thread-list function shape

## Current State

- Scheduled task editing currently requires manual `thread_id` input in `frontend/app/src/components/scheduled-task-editor.tsx`
- `GET /api/threads` already exists and returns threads owned by the current user
- Chat's cross-person picker is a `chat` picker, not a `thread` picker
- There is no existing backend concept of "threads visible to me but not owned by me"

## Approaches

### 1. Minimal extension of existing thread API

Keep `/api/threads`, add an optional `scope` query parameter, and introduce a reusable frontend thread picker that consumes it.

`scope=owned` returns the current behavior.
`scope=visible` is accepted as part of the contract but currently resolves to the same owned-thread set.

Pros:

- minimal backend churn
- no new domain model
- scheduled tasks can stop exposing raw `thread_id`
- creates the right interface shape for future expansion

Cons:

- `visible` is a forward-looking contract, not a distinct implementation yet

### 2. New dedicated endpoint for selector use

Add a new endpoint such as `/api/thread-options` and keep `/api/threads` unchanged.

Pros:

- avoids changing an existing endpoint

Cons:

- duplicates thread listing behavior
- creates another API surface for the same domain
- worse reuse story

### 3. Frontend-only fix

Leave backend unchanged and build a picker directly on top of existing `listThreads()`.

Pros:

- fastest initial patch

Cons:

- no reusable scope contract
- forces future Chat or panel consumers to re-invent filtering semantics

## Recommendation

Choose approach 1.

This is the smallest change that fixes the actual product problem and leaves a clean seam for later expansion.

## Design

### Backend

Keep `/api/threads` as the single list endpoint, but add:

- query parameter: `scope=owned|visible`

First-version behavior:

- `owned`: list threads owned by current user
- `visible`: return the same set as `owned` for now

Backend structure:

- extract thread listing assembly into a reusable helper function in `backend/web/routers/threads.py`
- keep auth behavior unchanged
- keep response shape unchanged so current consumers do not break

This is intentionally a contract-first change. The API shape becomes stable now, and the real `visible` semantics can be added later without rewriting consumers.

### Frontend

Add a reusable thread picker component based on the existing command-dialog search pattern.

The component should:

- accept `scope`
- fetch threads through `listThreads(scope)`
- show human-readable thread labels, not raw IDs
- return the selected `ThreadSummary`

The scheduled task editor should:

- replace freeform `thread_id` input with this picker
- store the selected thread's `thread_id` in the draft
- show the selected thread label and lightweight metadata
- keep the existing external link to inspect the selected thread

The initial reuse target is scheduled tasks only. The component should still be generic enough for later use elsewhere.

### Data and UX Rules

- scheduled task editor uses `scope="owned"`
- no manual freeform `thread_id` entry in normal flow
- if no threads exist, fail honestly in UI and point the user to create or open one first
- no fallback to hidden raw-ID input

## Error Handling

- invalid `scope` should fail with `400`
- network failures should surface clearly in the picker UI
- empty list should show a plain empty state

## Testing

Backend:

- `scope=owned` returns owned threads
- `scope=visible` currently matches owned threads
- invalid `scope` returns `400`

Frontend:

- `listThreads(scope)` builds the right request URL
- picker loads and displays thread options
- scheduled task editor saves selected thread into the draft
- empty and error states render visibly

## Non-Goals

- no new thread permission model
- no cross-user thread discovery
- no unification of thread and chat selection
- no scheduled-task domain changes beyond replacing thread selection UX
