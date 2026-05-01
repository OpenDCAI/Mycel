# YATU: External Runtime Inbox

## User Story

As an external code agent, I should receive runtime wake hints through a public
notification inbox while durable chat messages remain in the normal chat store.

## Product Surface

- Real Mycel backend from the current app branch.
- Installed `cel` CLI from the SDK repo.
- One human owner login and one local external-agent identity in `~/.mycel`.
- Local runtime daemon started through the installed `cel` CLI.
- Optional Claude Code or Codex provider hook using the launched external
  identity.

## Setup

1. Start the backend from the current app branch with the normal auth/runtime
   contract satisfied. If registration is part of the proof, `LEON_AVATAR_ROOT`
   must point to a writable avatar directory. If the host reaches Supabase
   through `http_proxy`/`https_proxy`, set `LEON_SUPABASE_HTTP_TRUST_ENV=1`.
2. Create or reuse a human owner login with `cel login`.
3. Create an external user from that owner with `cel agent external create ...`.
4. Start the local runtime daemon.
5. Launch the external runtime through `cel codex ...` or `cel claude ...`.
6. Create a direct or group chat that includes the external user.

## Flow

1. As another chat member, send a normal chat message to the chat.
2. Trigger the launched external process through a provider hook event. For a
   direct CLI probe, use `cel internal hook codex` or `cel internal hook claude`;
   the hook path must read local runtime IPC/cache, not open a backend wait.
3. Confirm the notification names event type, sender, and chat id but does not
   contain the chat message body.
4. Use `cel chat read <chat-id>` to inspect bodies and advance the read cursor.
5. Use `cel chat send <chat-id> "..."` to reply as the external user.
6. Trigger the hook again and confirm the already-read notification does not
   repeat.
7. Send several messages from the same sender in the same chat, reading between
   them, and confirm each fresh message still produces a fresh hook
   notification.
8. Stop the local runtime while a long-poll wait may still be in flight, send a
   new chat message to the external user, start the runtime again, then trigger
   the provider hook. The hook should surface the unread chat notification
   before the user calls `cel chat read`.

## WebSocket Stream Variant

1. Open `/api/runtime/inbox/subscribe` with the external user's token carried as
   `Sec-WebSocket-Protocol: bearer.<token>`.
2. Send a chat or relationship notification to that external user from another
   real user.
3. Confirm the socket receives a `notify` frame with a monotonic `seq`,
   `fingerprint`, timestamp, and metadata only.
4. Close the socket, send another notification, reconnect, and send
   `{"type":"resume","since_seq":<last-seen-seq>}`.
5. Confirm replay returns the missed frame in order. If replay retention is
   exceeded, confirm the socket reports `replay_overflow` and the local daemon
   falls back to authenticated HTTP drain for catch-up.

## Pass Criteria

- The external inbox item is produced by backend runtime delivery, not by a CLI
  polling shortcut.
- Chat notifications are recoverable from the user's unread chat projection.
  Queue entries are wake tokens, not the only durable source of truth for chat
  notification metadata.
- The hook drain is authenticated as the external user and only drains that
  user's local runtime inbox.
- The notification is metadata-only; chat bodies are read through chat APIs.
- Consecutive chat notifications are distinguished by stable message identity,
  not only by summary fields such as sender name or unread count.
- WebSocket steady-state delivery and HTTP drain catch-up share the same
  metadata projection and monotonic sequence source.
- A daemon restart does not lose a chat notification just because an old wait
  request consumed a wake token while the local daemon was stopping.
- The reply appears as a normal chat message from the external user's identity.

## Failure Signals

- The backend emits Claude-specific branches instead of a general external
  runtime inbox.
- Notification drain includes raw chat bodies or managed-agent prompt text.
- A stopped or crashing local daemon can make an unread chat permanently
  invisible to the next runtime drain.
- The external user can send as another user by passing sender ids.
- The test proves success through queue internals instead of product surfaces.
