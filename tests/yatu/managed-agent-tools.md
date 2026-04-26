# YATU: Managed-Agent Tools

## User Story

As a Mycel-managed agent, I should be able to participate in real product
workflows using tools: relationship review, chat join review, chat reading,
message sending, subagent work, and background command execution.

## Entry Surfaces

- Real managed-agent runtime thread.
- Real LLM model.
- Product chat messages and runtime notifications.
- Agent tool calls exposed by the backend runtime.

## Setup

1. Start backend from the branch under test.
2. Create a managed-agent user and runtime thread.
3. Ensure model credentials are live.
4. Create chats or requests that require the agent to act.

## User Loop

1. Send the managed agent a relationship request from an external profile.
2. Ask the agent naturally to inspect pending relationships and decide.
3. Ask the agent to read a chat, summarize unread messages, and reply.
4. Create a group join request for a group owned by the managed agent.
5. Ask the agent naturally to inspect join requests and approve or reject.
6. Ask the agent to run a small background command and report completion.
7. Ask the agent to delegate one bounded subtask to a subagent and report the
   result back in chat.

## Pass Bar

- The agent uses tools instead of hallucinating backend state.
- Relationship and join-request decisions persist in the backend.
- Background command completion is delivered back through the runtime.
- Subagent tool usage produces a visible result and does not block the parent
  indefinitely.
- All participant-visible information moves through chat or tool outputs, not
  hidden memory extraction.

## Pitfalls

- Do not replace the LLM with a fake model.
- Do not call the tool services directly from a test helper.
- Do not accept prompt echo as proof that a tool ran.
- If the agent cannot find the right tool, treat that as product/tooling
  feedback.
