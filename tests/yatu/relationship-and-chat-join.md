# YATU: Relationship Requests And Chat Join Requests

## User Story

As users and agents, we need two distinct request flows:

- relationship request: user-to-user social access
- chat join request: user-to-group membership

Approving one must not secretly approve the other.

## Entry Surfaces

- Frontend contacts and chat pages for human-facing proof.
- Installed `mycel` CLI for external-agent proof.
- Managed-agent relationship and chat-join tools when the target/owner is a
  Mycel-managed agent.
- Public backend APIs through the frontend/SDK/CLI only.

## Setup

1. Start the backend from the current branch.
2. Prepare a human profile that created an external-agent profile through the
   public auth onboarding surface, plus at least one managed-agent runtime
   thread.
3. Prepare one active group chat with a clear owner.
4. Prepare a non-member visitor profile.

## User Loop

### Relationship Request

1. External user requests a relationship with a managed agent and includes a
   short natural-language reason.
2. The managed agent receives the request notification, lists pending
   relationships through its tool, and approves or rejects.
3. The external user lists relationships through the CLI and observes the state.
4. If approved, the external user opens a direct chat and sends a message with
   an explicit mention to the managed agent.

### Chat Join Request

1. Visitor opens the group entry surface with `join-target` or the frontend
   group URL.
2. Visitor submits a natural-language request to join.
3. Group owner lists pending join requests through the frontend, CLI, or
   managed-agent tool.
4. Group owner approves the request.
5. Visitor reads and sends in the group as a real member.

## Pass Bar

- Relationship requester/approver identities come from token or managed-agent
  tool identity, not body arguments.
- Relationship request message is visible to the reviewer.
- Chat join request approval creates real membership.
- A rejected managed-agent chat-join requester is notified through runtime
  delivery even though it is not a group member.
- Notification delivery never replaces durable request state.

## Pitfalls

- Do not call storage repos or inspect DB rows as the test oracle.
- Do not approve a relationship and assume the user joined a group.
- Do not approve a join request and assume the users now have a relationship.
- Do not use a mock LLM for managed-agent approval behavior.
