# YATU: External User Auth Management

## User Story

As a human Mycel user, I want to create a durable external code-agent user from
my own account, then let that external user participate in chat as itself.

The human account manages the external user. The external user is still a real
chat user, not a managed Mycel agent and not an alias for the human.

## Entry Surfaces

- Public backend auth API through the generated SDK or installed `mycel` CLI.
- Public chat API through the generated SDK or installed `mycel` CLI.
- Frontend user/chat candidate surfaces when available.

## Setup

1. Start the backend from the current branch.
2. Log in as a human user and save a local owner profile.
3. Create one external code-agent user from that owner profile.
4. Save the returned external token into a separate external profile.

## User Loop

1. As the owner profile, inspect the owner identity.
2. As the owner profile, create the external user.
3. As the external profile, inspect identity and confirm the token resolves to
   the external user, not the owner.
4. As the owner profile, open the user/chat candidate surface and confirm the
   external user is manageable by this account without a relationship request.
5. As the external profile, request to join a group or send in a chat where it
   is already a member.
6. As a different user with no relationship/contact, confirm the external user
   is not implicitly available just because its creator is a user.

## Pass Bar

- The external user's management link is durable backend state.
- The external user's chat sender identity comes from its own token.
- The external user does not carry managed-agent runtime fields such as
  `owner_user_id` or `agent_config_id`.
- The CLI/SDK do not pass sender user ids in request bodies.
- The test never reads database rows directly as the proof.

## Pitfalls

- Do not treat a JWT claim alone as durable ownership proof.
- Do not reuse managed-agent `owner_user_id` for external users.
- Do not approve relationship or join requests by calling storage helpers.
- Do not make the CLI remember a private ownership concept that the backend
  cannot report.
