# Provider Hook Bootstrap Matrix YATU

## User Story

A user launches Codex or Claude Code through `cel codex` or `cel claude` from a
normal terminal, asks what Mycel is, and the provider already has the Mycel
runtime guidance in its real model context. The proof must survive terminal
differences and wrapper managers without relying on a debug-only hook command.

## Entry Surfaces

- Installed `cel` CLI from the SDK repo.
- Real Mycel backend from the current app branch.
- Real Codex CLI and Claude Code installs.
- Real terminal surfaces such as macOS Terminal, iTerm2, WezTerm, tmux, and a
  Linux shell. PowerShell is a later matrix row when a Windows host is
  available.

## Setup

1. Use an isolated `MYCEL_HOME` for each matrix row.
2. Log in through the public auth flow.
3. Create or select one external-agent identity per provider.
4. Launch the provider only through the public wrapper:
   `cel codex ...` or `cel claude ...`.
5. If a provider is itself launched through another wrapper manager, keep that
   manager enabled for at least one matrix row.

## User Loop

For every terminal/provider row:

1. Start a fresh provider session through `cel`.
2. Ask the provider: `Do you know what Mycel is in this session?`
3. Confirm the first real assistant answer describes the local Mycel CLI,
   identity, chat, and hook guidance instead of guessing a public project named
   Mycel.
4. Send one normal Mycel chat message to the external identity from another
   user.
5. Trigger a supported provider hook event through ordinary interaction, not a
   debug-only hook command.
6. Confirm the provider receives a metadata-only Mycel notification and then
   uses `cel chat read` before quoting message bodies.

## Pass Bar

- The bootstrap guidance reaches the provider's real first response.
- `SessionStart` success alone is not sufficient; the proof must include the
  first user prompt path.
- Hook suppression, caching, or wrapper-manager behavior cannot make the first
  real prompt lose Mycel guidance.
- The same runtime identity is used by the wrapper, hook, chat read, and chat
  send paths.
- Provider hooks read local runtime IPC/cache and do not open a backend wait as
  a shortcut.
- A failed terminal row records the terminal/provider/wrapper-manager tuple so
  the failure can be reproduced elsewhere.

## Pitfalls

- A provider answering from general internet knowledge about a different Mycel
  project fails the card.
- A one-shot `cel internal hook ...` probe is useful debugging, but it is not
  this YATU proof.
- Reading raw tmux or terminal scrollback as the only evidence fails the card;
  use the visible provider answer and public Mycel chat surfaces.
- Do not pass by editing provider prompts manually after launch.
