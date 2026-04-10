# Messaging Decoupling Roadmap

## Goal

Turn `messaging/` into the single owner of messaging-domain truth instead of a top-level directory that still shares live contracts with web routers and runtime tool glue.

This roadmap is intentionally scoped as a long-lived implementation lane, not a one-shot refactor. PR #272 started as a placeholder carrier for this document, and now also carries bounded implementation slices that stay inside the ownership plan below instead of letting each slice invent its own local truth.

Current campaign status:

1. Slice 1 resolver baseline landed via `6b8afffd`, introducing `messaging.display_user.resolve_messaging_display_user(...)` and cutting `MessagingService` over to the canonical resolver.
2. The router-side follow-up landed via `668894eb`, cutting `backend/web/routers/messaging.py` over to that same canonical resolver for its participant/display shell.
3. Visit-chat summary ownership landed via `f6310f7d`, moving visit-chat summary assembly into `MessagingService.list_chats_for_user(...)`.
4. Chat-detail ownership landed via `518598af`, making `MessagingService.get_chat_detail(...)` the canonical owner for visit-chat detail assembly.
5. Tool facade cutover landed via `9a9e493e`, so `ChatToolService` no longer talks directly to chat-member/message repos for live messaging operations.
6. `1c036453` is formatting-only and keeps the lane green without widening scope.

Current mainline ruling:

- This lane is no longer an active refactor campaign. The bounded slices above are landed on current mainline truth.
- The lane is now parked, not in-progress-by-inertia.
- Later branch-only follow-ups like `e230f275`, `c725e144`, `c4fc0d6b`, `c7ca7405`, `ee6374fd`, and `f8485886` are **not** part of current mainline truth and must not be treated as landed closure.

Current parking rule:

- later `chat_tool_service.py` ownership cleanup remains deferred
- delivery policy changes remain deferred
- frontend/sidebar work remains deferred
- future slices still require explicit bounded assignment rather than inertia from this roadmap
- if this lane is resumed, start from current mainline code, not from stale branch assumptions

## Why This Exists

The current codebase already treats `messaging/` as a bounded domain:

- web routers depend on it
- runtime chat tools depend on it
- realtime bridge depends on it
- relationship and delivery policy live under it

But the ownership is still split across multiple surfaces.

### Original ownership split this lane was created to fix

1. Canonical social/display resolution is duplicated.

- `messaging/service.py` owns `_resolve_display_user()`
- `messaging/tools/chat_tool_service.py` owns another `_resolve_display_user()`
- `backend/web/routers/messaging.py` used to own another resolver shell before `668894eb`

2. Conversation read-model ownership is split.

- `MessagingService.list_chats_for_user()` already wanted to assemble chat summaries
- `backend/web/routers/conversations.py` used to rebuild visit-chat title/avatar/unread data again before `f6310f7d`

3. Runtime chat tools bypass the messaging domain.

- `ChatToolService` consumes `MessagingService`
- but used to also talk directly to chat-member/message repos before `9a9e493e`

4. The domain still depends on web presentation glue.

- `messaging/service.py` imports `backend.web.utils.serializers.avatar_url`
- so the top-level domain is still coupled to web serialization concerns

These are not style issues. They are ownership failures: more than one live surface was acting like the source of truth.

### Current residual ownership split on mainline

1. Canonical social/display resolution is still duplicated between:

- `messaging/service.py`
- `messaging/tools/chat_tool_service.py`

2. Visit-chat summary ownership is no longer split.

- `MessagingService.list_chats_for_user()` now owns visit-chat summary assembly
- `backend/web/routers/conversations.py` only merges that visit projection with hire-thread rows

3. Runtime chat tools no longer bypass message/chat-member storage repos directly.

- `ChatToolService` now routes live messaging reads/sends/search through `MessagingService`
- but it still keeps a local display-user bridge instead of fully delegating that identity shell

4. The domain still depends on web presentation glue.

- `messaging/service.py` still imports `backend.web.utils.serializers.avatar_url`
- so the final domain/web boundary cleanup is still deferred

## Design Principles

This roadmap follows the same principles recorded in [AGENTS.md](../../AGENTS.md) and mined from `Vibe-Skills`:

1. Single source of truth
2. Ownership split and boundary clarity
3. Proof class over helper noise
4. Fail loud instead of preserving silent compatibility shells

## Target Ownership

The target state is narrow:

### `messaging/` owns

- social/display resolution for messaging identities
- visit-chat summary/read-model assembly
- messaging-facing delivery and relationship policy
- runtime-facing chat facade consumed by tools

### web routers own

- HTTP transport
- auth and route-local request validation
- response translation only where the outward contract is explicitly different

### runtime tool registration owns

- tool schema registration
- tool-mode registration
- tool argument parsing that is specific to tool UX

It should not own message history storage queries, chat membership queries, or identity resolution rules directly.

## Planned Slice Order

### Slice 1: Canonical messaging identity resolver

Create one canonical resolver inside `messaging/` for `social_user_id -> display user`.

Current lane status: partially landed on mainline.

This slice should delete duplicated resolver logic from:

- `messaging/service.py` @ landed on this lane in `6b8afffd`
- `backend/web/routers/messaging.py` @ landed on this lane in `668894eb`
- `messaging/tools/chat_tool_service.py` @ still deferred on current mainline
- `backend/web/routers/conversations.py` @ not a direct owner of messaging display resolution on current mainline

Stopline:

- do not widen outward payloads
- do not rewrite relationship or delivery policy
- do not touch frontend

### Slice 2: Visit-chat summary owner cutover

Make `MessagingService` the sole owner of visit-chat summary assembly:

- title
- avatar
- entities
- unread count
- last message
- updated timestamp

Then make `backend/web/routers/conversations.py` consume that projection instead of rebuilding it.

Current lane status: landed on mainline via `f6310f7d`.

Stopline:

- keep `/api/conversations` outward contract stable
- do not refactor hire-thread rows in the same slice
- do not mix in frontend sidebar work

### Slice 3: Tool facade cutover

Narrow `ChatToolService` so it consumes a messaging facade instead of talking directly to:

- chat-member repo @ landed via `9a9e493e`
- messages repo @ landed via `9a9e493e`
- thread repo @ still partially retained for local display-user bridging
- duplicated identity lookup @ still partially retained on current mainline

Stopline:

- keep tool names and tool schemas stable
- do not redesign range syntax or tool UX
- do not mix taskboard/runtime registry cleanup into this lane

### Slice 4: Domain/web boundary cleanup

After the above slices land, remove residual web-specific serialization leakage from `messaging/`, especially direct dependence on `backend.web.utils.serializers.avatar_url`.

Current lane status: not started on mainline.

Stopline:

- no broad serializer rework
- no frontend payload rename
- no “compat forever” fallback layer

## Non-Goals

This lane does not include:

- relationship state machine redesign
- delivery policy redesign
- frontend conversation/sidebar redesign
- taskboard contract cleanup
- messaging schema rewrite
- monitor/resource/provider/runtime bootstrap cleanup

## Evidence Standard

Each implementation slice should ship with one primary proof:

- a real caller proof if the slice changes a live caller contract
- otherwise a bounded integration proof around the new canonical owner

Do not justify the refactor with helper-only tests that merely prove delegation.

## Current File Hotspots

- [messaging/service.py](../../messaging/service.py)
- [messaging/tools/chat_tool_service.py](../../messaging/tools/chat_tool_service.py)
- [backend/web/routers/messaging.py](../../backend/web/routers/messaging.py)
- [backend/web/routers/conversations.py](../../backend/web/routers/conversations.py)
- [backend/web/core/lifespan.py](../../backend/web/core/lifespan.py)

## Placeholder PR Contract

The placeholder PR for this roadmap is allowed to carry:

- this roadmap document
- bounded implementation slices that stay inside the ownership plan above

It should not become a grab bag for unrelated communication cleanup.

## Bounded Slice Rule

This branch is no longer a pure docs-only shell. It is now a bounded implementation lane, with the following hard limits:

- keep implementation aligned to the ownership plan above
- do not widen from router/service identity cutover into `chat_tool_service.py`
- do not widen into `backend/web/routers/conversations.py` ownership surgery
- do not widen into delivery policy or frontend work
- no opportunistic tests or cleanup hitchhiking
- no parallel “helper roadmap” or scratchpad documents inside the repo
- future implementation still resumes only when the principal assigns a different bounded cut

## Current Truth Snapshot

This roadmap should be read as a parked checkpoint ledger, not as an active TODO list.

What is already true on current mainline:

- `MessagingService` owns canonical messaging display-user resolution.
- `backend/web/routers/messaging.py` uses that canonical resolver instead of a router-local duplicate.
- `MessagingService.list_chats_for_user(...)` owns visit-chat summary assembly consumed by `backend/web/routers/conversations.py`.
- `MessagingService.get_chat_detail(...)` owns visit-chat detail assembly.
- `ChatToolService` routes live messaging reads/sends/search through `MessagingService` instead of direct chat/message repo calls.

What is intentionally still not true on current mainline:

- `ChatToolService` still keeps a local `_resolve_display_user(...)` bridge.
- `messaging/service.py` still imports `avatar_url` from web serialization glue.
- delivery policy redesign is not part of this lane.
- frontend/sidebar work is not part of this lane.

If memory is lost later, the correct reading is:

- this lane produced bounded ownership cuts and then parked cleanly
- it is not waiting on a hidden “final sweep”
- any future resume must start from the residuals listed above, not from stale branch names or placeholder wording
