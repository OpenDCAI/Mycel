# YATU: Managed-Agent Word Chain

## User Story

As a user in a group chat with two Mycel-managed agents, I can start a word
chain with one natural sentence and the agents continue for several turns
without me coordinating each word.

## Product Surface

- Real Mycel backend from current `origin/dev`.
- Real Mycel-managed agents with LLM execution enabled.
- Public chat UI or public chat API/CLI.
- Durable chat messages visible to all group members.

## Setup

1. Start the backend from the current app branch.
2. Create or reuse one human/owner user.
3. Create two managed agents owned by that user.
4. Create a group chat containing the owner and both managed agents.
5. Ensure both managed agents can be woken by normal group-chat delivery.

## Flow

1. As the owner, send one natural-language message:

   ```text
   我们来玩成语接龙。你们两个轮流接，每次只发一个成语，至少接 8 轮。
   ```

2. Do not send per-turn instructions.
3. Watch the chat until the agents have had enough time to respond.
4. Read the final transcript through the same public chat surface.

## Pass Criteria

- The owner sends only the initial instruction.
- Both managed agents reply through the chat.
- The transcript contains at least 8 agent turns after the initial user message.
- Replies are visible as normal chat messages, not as hidden internal state.
- The test does not require manual per-word coordination.

## Failure Signals

- Only one agent wakes when the default group-chat behavior should wake both.
- The user has to mention every managed agent manually for the simple default
  group case.
- The workflow requires direct thread-memory reads or private agent state.
- The agents respond only when the tester sends one instruction per turn.
