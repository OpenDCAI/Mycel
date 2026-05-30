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
  ports/            checkpoint · event_bus  (+ executor, fs, storage TODO)
  loop.py           QueryLoop — core turn loop ONLY               [TODO: decompose]
  recovery/         model error-recovery strategies (optional)    [TODO: from loop.py]
  streaming.py      streaming tool-overlap engine (optional)      [TODO: from loop.py]
  adapters/         in-memory/sqlite checkpoint · null emitter ·   [TODO]
                    local executor · local filesystem
  multiagent/       spawn · bus · registry — lightweight handoff  [TODO]
  config/           config loaders (lifted from config/, clean)   [TODO]
  agent.py          thin assembly facade (replaces LeonAgent 1700L)[TODO: ~200L]
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

- **Phase 0 ✅** lift clean foundation; verify it imports standalone (done).
- **Phase 1** minimal runnable loop: core turn loop + in-memory checkpoint + null
  emitter + local executor + a few builtin tools → prove single agent runs end-to-end
  against a real model with no DB/web.
- **Phase 2** decompose recovery + streaming as optional layers; port middleware stack.
- **Phase 3** lightweight multi-agent (spawn + bus + registry + handoff).
- **Phase 4** thin facade + config; parity tests; adapter shims so Mycel's backend
  consumes `agent_core` (Postgres/SSE/supabase as adapters) without behavior change.

## Source provenance

Base: `OpenDCAI/Mycel` branch `dev` @ `4ec5a4d` (the live integration branch; `main`
is a stale 2026-04 snapshot with unrelated history — not used).
