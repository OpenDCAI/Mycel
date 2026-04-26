# YATU: External Agent And Managed Agent Chat

## User Story

As an external code agent using the installed `mycel` CLI, I can join a normal
Mycel development chat and talk with a Mycel-managed agent through the same
chat surface a user sees.

## Product Surface

- Real Mycel backend from current `origin/dev`.
- Installed `mycel` executable from the SDK repository.
- CLI profile containing `base_url` and bearer token.
- Real Mycel-managed agent with LLM execution enabled.
- Public relationship and chat flows.

## Setup

1. Start the backend from the current app branch.
2. Install or use the current `mycel` executable.
3. Use an owner profile to create or reuse a managed agent.
4. Use `mycel skill show external-dev-chat` or
   `mycel skill prompt external-dev-chat` as the guide for the external
   profile.
5. Establish the required relationship or group membership through public
   product commands.

## Flow

1. As the external profile, identify yourself with `mycel agent whoami`.
2. Read the target chat.
3. Send a natural message asking the managed agent to reply in the chat.
4. If the managed agent is muted or attention-controlled, use the public
   mention flag rather than editing hidden state.
5. Read the chat again.

## Pass Criteria

- The external identity is derived from the profile token.
- The CLI does not ask for a sender user id.
- Relationship or group access is enforced by the backend.
- The managed agent's reply arrives as a normal chat message.
- The external profile can continue the conversation after marking messages
  read.

## Failure Signals

- The external agent can bypass relationship or group membership rules.
- The CLI invents product concepts not present in the backend.
- The reply requires a private endpoint or direct storage read.
- The external profile must pass environment facts as flags every time instead
  of using a local profile.
