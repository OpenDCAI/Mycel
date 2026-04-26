# YATU: External Runtime Inbox

## User Story

As an external code agent, I should receive runtime wake hints through a public
notification inbox while durable chat messages remain in the normal chat store.

## Product Surface

- Real Mycel backend from the current app branch.
- Installed `mycel` CLI from the SDK repo.
- One human owner profile and one external-agent profile.
- Optional Claude Code hook adapter using the external profile.

## Setup

1. Start the backend from the current app branch.
2. Create or reuse a human owner profile.
3. Create an external user from that owner profile.
4. Save the external token into a CLI profile.
5. Create a direct or group chat that includes the external user.

## Flow

1. As another chat member, send a normal chat message to the chat.
2. As the external profile, run `mycel notify drain --format claude-context`.
3. Confirm the notification names event type, sender, and chat id but does not
   contain the chat message body.
4. Use `mycel chat messages list <chat-id>` to inspect bodies.
5. Use `mycel chat read <chat-id>` before replying.
6. Use `mycel chat send <chat-id> "..."` to reply as the external user.

## Pass Criteria

- The external inbox item is produced by backend runtime delivery, not by a CLI
  polling shortcut.
- The notification drain is authenticated as the external user and only drains
  that user's inbox.
- The notification is metadata-only; chat bodies are read through chat APIs.
- The reply appears as a normal chat message from the external user's identity.

## Failure Signals

- The backend emits Claude-specific branches instead of a general external
  runtime inbox.
- Notification drain includes raw chat bodies or managed-agent prompt text.
- The external user can send as another user by passing sender ids.
- The test proves success through queue internals instead of product surfaces.
