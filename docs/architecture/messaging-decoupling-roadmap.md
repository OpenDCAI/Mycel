# Messaging Decoupling Roadmap

## Goal

Turn `messaging/` into the single owner of messaging-domain truth instead of a top-level directory that still shares live contracts with web routers and runtime tool glue.

This roadmap is intentionally scoped as a long-lived implementation lane, not a one-shot refactor. The initial placeholder PR should carry this document plus follow-up implementation slices, rather than letting each slice invent its own local truth.

Current campaign ruling: this branch remains a docs-only shell until the principal assigns the first bounded implementation slice. The roadmap is canonical direction for the lane, not standing permission to start Slice 1.

## Why This Exists

The current codebase already treats `messaging/` as a bounded domain:

- web routers depend on it
- runtime chat tools depend on it
- realtime bridge depends on it
- relationship and delivery policy live under it

But the ownership is still split across multiple surfaces.

### Current split ownership

1. Canonical social/display resolution is duplicated.

- `messaging/service.py` owns `_resolve_display_user()`
- `messaging/tools/chat_tool_service.py` owns another `_resolve_display_user()`
- `backend/web/routers/conversations.py` owns a third `_resolve_display_user()`

2. Conversation read-model ownership is split.

- `MessagingService.list_chats_for_user()` already assembles chat summaries
- `backend/web/routers/conversations.py` rebuilds visit-chat title/avatar/unread data again

3. Runtime chat tools bypass the messaging domain.

- `ChatToolService` consumes `MessagingService`
- but also talks directly to chat-member/message/thread repos

4. The domain still depends on web presentation glue.

- `messaging/service.py` imports `backend.web.utils.serializers.avatar_url`
- so the top-level domain is still coupled to web serialization concerns

These are not style issues. They are ownership failures: more than one live surface is acting like the source of truth.

## Design Principles

This roadmap follows the same principles recorded in [AGENTS.md](/Users/lexicalmathical/worktrees/leonai--messaging-decouple-placeholder/AGENTS.md) and mined from `Vibe-Skills`:

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

This slice should delete duplicated resolver logic from:

- `messaging/service.py`
- `messaging/tools/chat_tool_service.py`
- `backend/web/routers/conversations.py`

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

Stopline:

- keep `/api/conversations` outward contract stable
- do not refactor hire-thread rows in the same slice
- do not mix in frontend sidebar work

### Slice 3: Tool facade cutover

Narrow `ChatToolService` so it consumes a messaging facade instead of talking directly to:

- chat-member repo
- messages repo
- thread repo
- duplicated identity lookup

Stopline:

- keep tool names and tool schemas stable
- do not redesign range syntax or tool UX
- do not mix taskboard/runtime registry cleanup into this lane

### Slice 4: Domain/web boundary cleanup

After the above slices land, remove residual web-specific serialization leakage from `messaging/`, especially direct dependence on `backend.web.utils.serializers.avatar_url`.

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

- [service.py](/Users/lexicalmathical/worktrees/leonai--dev-feature/messaging/service.py#L58)
- [service.py](/Users/lexicalmathical/worktrees/leonai--dev-feature/messaging/service.py#L170)
- [chat_tool_service.py](/Users/lexicalmathical/worktrees/leonai--dev-feature/messaging/tools/chat_tool_service.py#L111)
- [chat_tool_service.py](/Users/lexicalmathical/worktrees/leonai--dev-feature/messaging/tools/chat_tool_service.py#L143)
- [chat_tool_service.py](/Users/lexicalmathical/worktrees/leonai--dev-feature/messaging/tools/chat_tool_service.py#L215)
- [conversations.py](/Users/lexicalmathical/worktrees/leonai--dev-feature/backend/web/routers/conversations.py#L25)
- [conversations.py](/Users/lexicalmathical/worktrees/leonai--dev-feature/backend/web/routers/conversations.py#L97)
- [lifespan.py](/Users/lexicalmathical/worktrees/leonai--dev-feature/backend/web/core/lifespan.py#L82)

## Placeholder PR Contract

The placeholder PR for this roadmap should be allowed to carry:

- this roadmap document
- subsequent implementation slices that stay inside the ownership plan above

It should not become a grab bag for unrelated communication cleanup.

## Freeze Rule

Until the first bounded slice is explicitly assigned, this branch is frozen as:

- one repo-shipping architecture roadmap
- do not start Slice 1 implementation yet
- no production-code changes
- no opportunistic tests or cleanup hitchhiking
- no parallel “helper roadmap” or scratchpad documents inside the repo
