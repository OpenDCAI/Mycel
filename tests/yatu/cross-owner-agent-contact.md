# YATU: Cross-Owner Agent Contact

## User Story

Two different Mycel owners want their agents to discover each other, establish
the right relationship or group membership, and keep talking through normal
chat. The proof must show that local aliases are only convenience handles and
that backend user ids remain the durable identity truth.

## Entry Surfaces

- Real backend process from the current branch.
- Installed `cel` CLI or SDK against that backend.
- Two owner accounts or two isolated owner homes.
- At least one agent identity under each owner. Either managed agents or
  external agents are acceptable, but the proof must include the runtime launch
  surface for any external agent.
- Public relationship, group, chat, and agent commands.

Do not use direct DB edits, copied local identity files, or hidden membership
inserts as proof.

## Setup

1. Start the current-branch backend with the real schema.
2. Prepare two isolated owner environments, such as `MYCEL_HOME=/tmp/owner-a`
   and `MYCEL_HOME=/tmp/owner-b`.
3. Log in both owners through the public auth flow.
4. Create or identify one agent user for each owner.
5. Record both the local alias and the resolved backend user id for each agent
   using public `cel agent show` / `cel agent list` style surfaces.

## User Loop

1. From owner A, address owner B's agent by the backend user id and initiate a
   relationship request or group invite through public commands.
2. From owner B, read the pending request using public commands and accept it.
3. Create or open a shared chat visible to both agents.
4. Launch the external-agent runtime for each side if the agents are external,
   using the normal `cel codex ...` or `cel claude ...` wrapper.
5. Send a message from agent A to agent B through the public chat surface.
6. Read the message from owner B's environment and reply from agent B.
7. Repeat one message using a local alias from the sender's own home and confirm
   the command output makes the resolved backend user id visible enough to catch
   a mistaken alias.
8. Delete or rename one local alias, then prove the chat and relationship still
   work when addressed by backend user id.

## Pass Bar

- The two owners cannot see or mutate each other's private local identity
  files.
- Local aliases never become global authority; backend user ids remain usable
  anywhere a user id is accepted.
- A local alias collision under different owners does not route to the wrong
  backend user.
- Relationship or group membership is enforced before chat delivery.
- Messages between agents appear as normal chat messages with ordinary read
  cursors and sender identities.
- Runtime wake is best-effort transport behavior; the durable proof is the
  backend chat and membership state.

## Pitfalls

- Passing only with copied `~/.mycel` state fails the card.
- Passing only because both agents run under one owner fails the card.
- A local alias silently shadowing a backend user id without showing the
  resolved backend id is a UX failure.
- A direct runtime inbox injection without a corresponding chat message is not
  cross-owner contact proof.
- Direct storage inspection may debug a failure, but it cannot be the proof.
