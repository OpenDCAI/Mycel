# YATU: Multi-Agent Natural-Language Workflows

## User Story

As a user orchestrating many agents, I should be able to run complex workflows
through ordinary chat messages, not by pulling private state out of agents.

## Entry Surfaces

- Real backend and managed-agent runtime.
- Installed `mycel` CLI or public SDK.
- Real chat messages and read-before-send loops.
- Real managed-agent LLM replies.

## Workflow A: Debate Tournament

1. Create or choose 16 managed agents.
2. Create a tournament chat or per-match chats.
3. Announce the bracket in natural language.
4. For each match, ask two agents to debate.
5. Ask non-debating agents to vote by ordinary chat replies.
6. Announce winners and advance the bracket.
7. Continue until one winner remains.

Pass bar:

- Agents see prompts through chat.
- Votes are visible messages.
- The organizer can reconstruct winners from chat transcript.
- No internal memory or DB row is used as participant communication.

## Workflow B: Guess The Average

1. Chair asks every participant to secretly choose a number from 1 to 100 and
   send it in chat.
2. Chair computes the average from visible replies.
3. Chair announces the closest participant and gives a short comment.
4. Repeat three rounds.
5. Chair comments on how the group average changed.

Pass bar:

- No structured-output contract is required.
- All guesses are ordinary chat text.
- Chair can compute from visible messages only.
- The workflow remains short enough that SDK/CLI friction is obvious.

## Pitfalls

- Do not mute everyone and then expect mention to wake muted agents. Mute is
  receiver-side quiet mode.
- Do not add workflow-specific backend concepts for tournament or average
  games.
- If orchestration requires long glue code, improve base chat/SDK primitives.

## Historical Seeds

- `~/share/yatu/debate-tournament-cli-20260426T-fanout-race-fix-v4/summary.md`
- `$MYCEL_WORKSPACE/notes/2026-04-25-sdk-yatu-16-agent-debate-tournament-plan.html`
- `$MYCEL_WORKSPACE/notes/2026-04-26-16-agent-debate-yatu-findings.html`
- `~/share/yatu/sdk-guess-average-workflow-20260425T230405Z/summary.md`
- `~/share/yatu/debate-tournament-cli-20260426T0333/summary.md`
- `~/share/yatu/debate-tournament-cli-20260426T200308-mute-control/summary.md`
