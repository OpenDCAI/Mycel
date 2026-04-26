# Mycel App YATU Tests

YATU means **You As The User**.

These files are product test cards, not automation scripts. A YATU card tells a
human or code agent how to exercise Mycel through real user surfaces:

- real backend process from the current branch
- real frontend browser when the card is frontend-facing
- real `mycel` CLI or SDK when the card is external-agent-facing
- real Mycel-managed agents with a real LLM when agent behavior matters
- real read-before-send loops through chat messages

Do not use mocks, DB peeking, internal agent memory transfer, direct helper
calls, or backend-only shortcuts as proof for these cards.

## Where Results Go

Do not write run results into these cards. Put artifacts under `~/share/yatu`
with a timestamped folder, and write a short result note outside the repo if a
run needs explanation.

Good artifact examples:

- `~/share/yatu/mention-wake-postmerge-20260426T031323Z`
- `~/share/yatu/managed-agent-relationship-cli-20260426T011838`
- `~/share/yatu/frontend-relationship-join-currentdev-20260426T`

## How To Read A Card

Each card has:

- **User story**: what a real user is trying to do.
- **Entry surfaces**: product surfaces allowed for the proof.
- **Setup**: what must exist before the first action.
- **User loop**: natural actions to perform.
- **Pass bar**: what a user should be able to observe.
- **Pitfalls**: known mistakes that invalidate the proof.

If a card is painful to run, do not add private glue to the test. Treat that as
product/API feedback and improve the underlying surface.

