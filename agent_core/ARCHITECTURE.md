# agent_core — architecture

A clean, minimal, multi-agent agent runtime extracted from Mycel's `core/runtime`.
Strategy: **hybrid** — lift the already-clean skeleton, decompose the God-objects,
redesign multi-agent to be lightweight. Lives as a top-level package inside Mycel
(branch `feat/agent-core`), can graduate to its own repo once stable.

## Principle: ports & adapters

The core depends only on `langchain_core.messages` + `pydantic` + stdlib. Every
contact with the outside world (persistence, event delivery, shell/fs execution)
goes through a **port** (Protocol/ABC). Concrete `adapters` are chosen at assembly
time. Result: the loop runs with no DB and no web server; Mycel's Postgres/SSE
become *one* set of adapters, not a hard dependency.

## Module map

```
agent_core/
  state.py          AppState · BootstrapConfig · ToolUseContext   [lifted, clean]
  tool_result.py    ToolResultEnvelope + helpers                  [lifted, clean]
  registry.py       ToolRegistry · ToolEntry · ToolMode           [lifted, clean]
  runner.py         ToolRunner — validate/permission/dispatch     [lifted, clean]
  validator.py      JSON-schema input validation                 [lifted, clean]
  permissions.py    ToolPermissionContext                         [lifted, clean]
  abort.py errors.py visibility.py                                [lifted, clean]
  middleware/       AgentMiddleware contract (wrap_model/tool_call)[lifted, clean]
  ports/            checkpoint · event_bus  (+ executor/fs/storage follow-on)
  loop.py           QueryLoop — core turn loop ONLY (~330L)        [done]
  agent.py          thin assembly facade (replaces LeonAgent 1700L, ~90L) [done]
  builtins/         workspace-contained fs + bash tools            [done]
  adapters/         InMemoryCheckpointStore · NullEventBus         [done]
  models.py         optional langchain init_chat_model helper      [done]
  multiagent/       bus · steering · registry · runtime · tools    [done]
  recovery/         RetryMiddleware (canonical optional layer)     [done]
  streaming.py      token-level tool-overlap engine                [follow-on]
```

## God-object decomposition (the "代码极简" work)

- **loop.py (92K, ~10 concerns)** → `loop.py` keeps ONLY the turn loop
  (LLM call → tool dispatch → advance → terminate). Pulled out into optional layers:
  error-recovery state machine → `recovery/`; streaming-tool-overlap → `streaming.py`;
  checkpoint hydrate/save → behind the `CheckpointStore` port; permission plumbing →
  already lives in `ToolRunner`; memory-compaction & notification-followthrough →
  middleware. Target: loop core ≈ 200–300 lines.
- **agent.py / LeonAgent (72K)** → thin `agent.py` facade that wires loop + registry +
  middleware + adapters from a small config object. Config resolution → `config/`.
- **service.py / AgentService (53K)** → `multiagent/`: a sub-agent is a *new loop*
  sharing the parent's model client + filtered registry + bus (NOT a rebuilt agent);
  handoff via an in-memory message bus + simple active-agent registry.

## Roadmap

- **Phase 0 ✅** lift clean foundation; verify it imports standalone.
- **Phase 1 ✅** minimal turn loop + in-memory checkpoint + null emitter; runs
  end-to-end against a (fake) model with no DB/web. `loop.py`, `adapters/`.
- **Phase 2 ✅** thin `Agent` facade + builtin tools (fs/bash) + optional model
  factory. `agent.py`, `builtins/`, `models.py`.
- **Phase 3 ✅** lightweight multi-agent (spawn + bus + registry + handoff).
  `multiagent/`.
- **Phase 4 ✅** optional layers (`recovery/RetryMiddleware`), README, full test
  suite (16 tests, fake models, no API).

### Follow-ons (not yet done)
- Token-level streaming (`streaming.py`) — the loop currently streams per-turn
  events; token streaming needs the tool-overlap engine, deferred as optional.
- Backend cutover: make Mycel's backend consume `agent_core` via adapter shims
  (Postgres checkpoint store, SSE event bus) — a separate integration effort.
- Richer optional middleware (prompt caching, memory compaction) + more builtin
  tools (search/LSP/web/MCP), lifted from `core/` as needed.

## Source provenance

Base: `OpenDCAI/Mycel` branch `dev` @ `4ec5a4d` (the live integration branch; `main`
is a stale 2026-04 snapshot with unrelated history — not used).
