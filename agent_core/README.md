# agent_core

A clean, minimal, multi-agent agent runtime — extracted and refactored from
Mycel's `core/runtime`. Depends only on `langchain_core` + `pydantic` (+ the
chosen model SDK). No DB, web server, or message bus required to run.

## Why

Mycel's agent worked but the runtime had grown into God-objects (a 92K-line loop,
a 72K-line agent factory). `agent_core` keeps the proven pieces — the tool
registry, the middleware contract, the turn loop — and re-homes the cross-cutting
machinery (streaming, error recovery, memory, notifications) into **optional
layers** behind ports. The result runs standalone and reads top-to-bottom.

## Single agent

```python
from agent_core import Agent
from agent_core.builtins import default_toolset
from agent_core.models import build_chat_model   # optional langchain helper

model = build_chat_model("claude-opus-4-8", model_provider="anthropic")
agent = Agent(
    model=model,                                 # any obj with .bind_tools + .ainvoke
    tools=default_toolset("/path/to/workspace"),
    system_prompt="You are a helpful coding agent.",
)

result = await agent.ainvoke("read main.py and summarize it")
print(result["messages"][-1].content)

# or stream per-turn events
async for event in agent.astream("do the thing"):
    ...   # {"agent": {"messages": [...]}} / {"tools": {"messages": [...]}}
```

Persistence is opt-in via a `CheckpointStore`:

```python
from agent_core.adapters import InMemoryCheckpointStore
agent = Agent(model=model, tools=..., checkpoint_store=InMemoryCheckpointStore())
await agent.ainvoke("...", thread_id="conv-1")   # resumes that thread next time
```

## Multi-agent (spawn + handoff)

```python
from agent_core.multiagent import MultiAgentRuntime
from agent_core.builtins import default_toolset

runtime = MultiAgentRuntime(
    model=model,
    tool_factory=lambda subagent_type: default_toolset("/work"),
)
orchestrator = runtime.build_agent(name="orchestrator")
await orchestrator.ainvoke("delegate the research, then summarize")
```

The orchestrator gets `spawn_agent`, `send_message`, `task_output` tools. A
sub-agent is a fresh loop sharing the same model client (not a rebuilt agent);
`send_message` routes through an in-memory bus that `SteeringMiddleware` drains
before each turn.

## Extending

- **Tools** — register `ToolEntry`s in a `ToolRegistry`. Same shape as Mycel's.
- **Middleware** — subclass `AgentMiddleware` (`wrap_model_call` / `wrap_tool_call`
  / `before_model`). `ToolRunner` (validation + permissions + dispatch) is one.
  `RetryMiddleware` (`agent_core.recovery`) is the canonical optional layer.
- **Ports** — swap `CheckpointStore` / `EventBusPort` for your infra (e.g. a
  Postgres checkpoint store, an SSE event bus) without touching the core.

## Layout & status

See `ARCHITECTURE.md`. Phases 0–4 (foundation, loop, facade, multi-agent,
optional layers) are implemented and tested; token-level streaming and the
Mycel-backend cutover are noted there as follow-ons.

## Tests

Pure, fast, no API calls (scripted fake models):

```bash
python agent_core/tests/run.py        # or import agent_core.tests.test_* and call test_*()
```
