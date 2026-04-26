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

## Workflow C: Open-Scope Chengyu Chain

1. Create or choose a group chat with multiple live managed agents.
2. Send one ordinary natural-language message asking the group to play 成语接龙.
3. Do not mention or individually coordinate agents.
4. Wait for the group to respond through ordinary chat.

Pass bar:

- The owner message has no mentions.
- At least two managed agents reply from that single group message.
- Follow-up interaction can continue without the owner spelling out every word.
- The transcript is readable from normal chat history.

## Pitfalls

- Do not mute everyone and then expect mention to wake muted agents. Mute is
  receiver-side quiet mode.
- Do not add workflow-specific backend concepts for tournament or average
  games.
- If orchestration requires long glue code, improve base chat/SDK primitives.
