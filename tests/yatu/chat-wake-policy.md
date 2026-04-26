# YATU: Chat Wake Policy

## User Story

As a group owner, I want a normal group message to wake all default Mycel agents,
but an explicitly mentioned message should wake only the mentioned default
agents. Everyone still receives the persisted chat message.

## Entry Surfaces

- Real Mycel backend from the current branch.
- Installed `mycel` CLI.
- Real Mycel-managed agents with runtime threads.
- Chat message list/read/send surfaces only.

## Setup

1. Start the backend from the branch under test.
2. Use an owner profile with a valid token.
3. Create or choose three managed-agent users with live runtime threads.
4. Create one group chat containing the owner and all three agents.
5. Confirm the owner can run `mycel agent whoami`, `mycel chat read`, and
   `mycel chat messages list`.

## User Loop

1. Mark the group chat read as the owner.
2. Send a natural-language message mentioning only Agent 1 and Agent 2 by
   passing `--mention <agent-1-id>` and `--mention <agent-2-id>`.
3. Wait long enough for managed-agent runtime replies.
4. Read the chat transcript as the owner.
5. Mark the group chat read again.
6. Send a second natural-language message with no `--mention`.
7. Wait again and read the transcript.

## Pass Bar

- The first send stores `mentioned_ids` for only Agent 1 and Agent 2.
- Before the second send, only Agent 1 and Agent 2 reply.
- Agent 3 remains quiet before the open-scope message.
- The second send has no mentions.
- After the second send, Agent 1, Agent 2, and Agent 3 can all reply.
- Message visibility and read/unread behavior are still normal chat behavior;
  wake policy only changes runtime interruption.

## Pitfalls

- Typing `@agent-id` in message text is not a mention. Use the CLI/API mention
  field.
- Do not inspect runtime queue internals to decide pass/fail.
- Do not treat duplicate follow-up chatter by already-woken agents as a
  wake-scope failure unless an unmentioned quiet agent speaks before it should.

## Historical Seeds

- `$MYCEL_WORKSPACE/notes/2026-04-26-chat-wake-policy-postmerge-yatu.html`
- `~/share/yatu/mention-wake-postmerge-20260426T031323Z`
