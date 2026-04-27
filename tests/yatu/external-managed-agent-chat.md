# YATU: External Agent And Managed Agent Chat

## User Story

As an external code agent using the installed `cel` CLI, I can join a normal
Mycel development chat and talk with a Mycel-managed agent through the same
chat surface a user sees.

## Product Surface

- Real Mycel backend from current `origin/dev`.
- Installed `cel` executable from the SDK repository.
- Global `~/.mycel` owner login and local external-agent identity.
- Real Mycel-managed agent with LLM execution enabled.
- Public relationship and chat flows.

## Setup

1. Start the backend from the current app branch.
2. Install or use the current `cel` executable.
3. Use `cel login` and `cel agent external create ...` to prepare the human
   owner and external-agent identities.
4. Launch the external agent with `cel codex ...` or `cel claude ...` so its
   runtime identity is injected.
5. Establish the required relationship or group membership through public
   product commands.

## Flow

1. Inside the launched external-agent process, identify yourself with
   `cel agent show`.
2. Read the target chat with `cel chat show <chat-id>`.
3. Send a natural message asking the managed agent to reply in the chat with
   `cel chat send <chat-id> "..."`.
4. If the managed agent is muted or attention-controlled, use the public
   mention flag rather than editing hidden state.
5. Read the chat again.

## Pass Criteria

- The external identity is derived from the launched local identity token.
- The CLI does not ask for a sender user id.
- Relationship or group access is enforced by the backend.
- The managed agent's reply arrives as a normal chat message.
- The external identity can continue the conversation after marking messages
  read.

## Failure Signals

- The external agent can bypass relationship or group membership rules.
- The CLI invents product concepts not present in the backend.
- The reply requires a private endpoint or direct storage read.
- The external agent must pass environment facts as flags every time instead of
  using the local identity selected by `cel codex ...` or `cel claude ...`.
