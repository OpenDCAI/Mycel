# Mycel Product Primitives

🇬🇧 English | [🇨🇳 中文](../zh/product-primitives.md)

## Core Philosophy

> An Agent has all the capabilities it needs -- the key is whether it has the corresponding resources.

Capabilities are innate; resources are granted. With resources, an agent can act. Without them, it cannot.

## Six Primitives

| Primitive | Term | Meaning | Example |
|-----------|------|---------|---------|
| **Thread** | Thread | A single interaction session | A user's conversation with an Agent |
| **Member** | Member | The Agent performing work | Main Agent, Sub-Agent |
| **Task** | Task | Work to be completed | User instructions, decomposed subtasks |
| **Resource** | Resource | A fundamental interaction surface available to the Agent | File system, terminal, browser, phone |
| **Connection** | Connection | An external service the Agent connects to | GitHub, Slack, Jira (MCP) |
| **Model** | Model | The AI brain | Mini / Medium / Large / Max |

### Relationship Diagram

```
Thread
├── Member (who does the work)
│   ├── Main Agent
│   └── Sub-Agent × N
├── Task (what to do)
│   ├── Task A → assigned to Member 1
│   └── Task B → assigned to Member 2
├── Resource (what to use) ← usage rights assigned to Members
│   ├── File system
│   ├── Terminal
│   └── Browser
├── Connection (which external services are connected)
│   ├── GitHub
│   └── Slack
└── Model (which brain to think with)
```

## The Essential Difference Between "Resources" and "Connections"

### Resource

The **fundamental channels** through which an Agent interacts with the world. Each resource opens an entire interaction dimension:

| Resource | World It Opens | What the Agent Can Do |
|----------|---------------|----------------------|
| File system | Data world | Read/write files, manage projects |
| Terminal | Command world | Execute system commands, run programs |
| Browser | Web world | Browse pages, operate web applications |
| Phone | App world | Operate mobile apps, test applications |
| Camera | Visual world | See the physical environment (future) |
| Microphone | Audio world | Receive voice input (future) |

### Connection

**External services** the Agent connects to (via MCP protocol). Point-to-point data channels:

- GitHub, Slack, Jira, databases, Supabase, etc.
- Plug one in, gain one more; unplug it, lose one
- Does not change the Agent's interaction dimensions -- only adds information sources

### Distinction Criteria

| | Resource | Connection |
|---|---|---|
| Essence | Interaction dimension | Data pipeline |
| Granularity | An entire world | A single service |
| Interaction mode | Perception + control | Request-response |
| User perception | "What the Agent can do" | "What services the Agent is connected to" |

## Ownership and Usage Rights

- The platform/user **owns** resources (ownership)
- When a thread is created, it **authorizes** which resources are available (usage rights)
- The main Agent can **delegate** resource usage rights to Sub-Agents
- Different Agents can have different resource permissions

## Resource Page Design Direction

### Principles

1. **Resources are the star, Providers are implementation details** -- Users care about "what the Agent has", not "which cloud vendor it uses"
2. **Atomic granularity** -- Each resource is presented independently, enabled/disabled independently
3. **Provider abstraction** -- Don't expose configuration forms; use icons + cards instead

### User Perspective (Goal)

```
Resources                          Source
├── ✓ File system  ~/projects/app    Local
├── ✓ Terminal                       Local
├── ○ Browser (click to enable)      Playwright
└── ○ Phone (click to connect)       Not configured

Connections
├── ✓ GitHub
├── ✓ Supabase
└── ○ Slack (not connected)
```

### Where Providers Fit

Providers (Local / AgentBay / Docker / E2B / Daytona) determine **where the file system and terminal come from**:

- Choose Local → File system = local disk, Terminal = local shell
- Choose AgentBay → File system = cloud VM, Terminal = cloud shell, + Browser
- Choose Docker → File system = inside container, Terminal = container shell

A Provider is a **source attribute** of a resource, not a top-level concept. It appears in settings as "Runtime Mode":

```
Runtime Mode
  ● Local (file system and terminal on your computer)
  ○ Cloud (file system and terminal on a cloud machine)
```

### Abstracting the Capability Matrix

The problem with the current design (provider × capability matrix table):
- The perspective is Provider-first ("what does this Provider support")
- It should be Resource-first ("I need this resource -- who can provide it")
- The dot matrix is too "database-style" -- should be replaced with icons + cards + toggles

## Terminology Mapping

| User Sees | Code / Technical Concept | Notes |
|-----------|-------------------------|-------|
| Resource | Sandbox capabilities | File system, terminal, browser, phone |
| Connection | MCP Server | External service integration |
| Runtime Mode | Sandbox Provider | Local / AgentBay / Docker |
| Thread | Thread | thread_id |
| Member | Agent / Sub-Agent | LeonAgent instance |
| Task | Task | TaskMiddleware |
| Model | Model | leon:mini/medium/large/max |

## Design Anti-Patterns

- Do not use the word "sandbox" in the user interface
- Do not make users choose a Provider every time they create a new thread
- Do not expose Provider configuration forms directly to users
- Do not conflate resources and connections (they are different layers)
