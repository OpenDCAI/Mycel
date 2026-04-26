# YATU: Frontend Social Flows

## User Story

As a human user, I should be able to discover people, request a relationship,
review incoming requests, open chats after approval, and request to join a group
without knowing backend vocabulary.

## Entry Surfaces

- Real browser via Playwright CLI.
- Frontend app from the current branch.
- Real backend from the current branch.
- Real user sessions and storage state.

## Setup

1. Start backend and frontend on non-overlapping ports.
2. Create or reuse real users with valid tokens.
3. Use browser sessions for requester, target, group owner, and visitor.
4. Keep CLI/API setup only for seeding users or profiles; all observed product
   proof must be through the browser.

## User Loop

1. Requester opens contact discovery or contacts surface.
2. Requester sends a relationship request with a natural-language message.
3. Target opens contacts/detail and sees the pending request message.
4. Target approves.
5. Requester opens a direct chat from the UI.
6. Visitor opens a group link or group URL while not a member.
7. Visitor submits a group join request.
8. Group owner opens the group page, sees the pending request, and approves.
9. Visitor reloads and can read/send as a member.

## Pass Bar

- Product text distinguishes relationship access from group membership.
- Pending relationship messages are visible in list/detail surfaces.
- Group join request form is usable from a non-member entry.
- Owner approval changes the visitor's visible chat state without manual DB
  changes.
- Browser screenshots or YAML snapshots show the user-visible state.

## Pitfalls

- Playwright CLI/browser proof is required. Backend responses alone are not
  frontend YATU.
- Do not use Playwright MCP as the product proof surface.
- Do not hide network or console errors when the browser looks visually fine.

## Historical Seeds

- `~/share/yatu/mycel-relationship-frontend-20260425T214005`
- `~/share/yatu/frontend-relationship-join-currentdev-20260426T`
- `~/share/yatu/frontend-social-discovery-20260426T0542`
- `~/share/yatu/frontend-join-request-ui-20260425T183836Z`

