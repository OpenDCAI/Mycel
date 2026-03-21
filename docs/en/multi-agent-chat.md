English | [中文](../zh/multi-agent-chat.md)

# Multi-Agent Chat

Mycel includes an Entity-Chat system that enables structured communication between humans and AI agents, and between agents themselves. This guide covers the core concepts, how to create agents, and how the messaging system works.

## Core Concepts

The Entity-Chat system has three layers:

### Members

A **Member** is a template -- the "class" that defines an agent's identity and capabilities. Members are stored as file bundles under `~/.leon/members/<member_id>/`:

```
~/.leon/members/m_AbCdEfGhIjKl/
  agent.md        # Identity: name, description, model, system prompt (YAML frontmatter)
  meta.json       # Status (draft/active), version, timestamps
  runtime.json    # Enabled tools and skills
  rules/          # Behavioral rules (one .md per rule)
  agents/         # Sub-agent definitions
  skills/         # Skill directories
  .mcp.json       # MCP server configuration
```

Member types:
- `human` -- A human user
- `mycel_agent` -- An AI agent built with Mycel

Each agent member has an **owner** (the human member who created it). The built-in `Mycel` member (`__leon__`) is available to everyone.

### Entities

An **Entity** is a social identity -- the "instance" that participates in chats. Think of it as a profile in a messaging app.

- Each Member can have multiple Entities (e.g., the same agent template deployed in different contexts)
- An Entity has a `type` (`human` or `agent`), a `name`, an optional avatar, and a `thread_id` linking it to its agent brain
- Entity IDs follow the format `{member_id}-{seq}` (member ID + sequence number)

The key distinction: **Member = who you are. Entity = how you appear in chat.**

### Threads

A **Thread** is an agent's running brain -- its conversation state, memory, and execution context. Each agent Entity is bound to exactly one Thread. When a message arrives, the system routes it to the Entity's Thread, waking the agent to process it.

Human Entities do not have Threads -- humans interact through the Web UI directly.

## Architecture Overview

```
Human (Web UI)
    |
    v
[Entity: human] ---chat_send---> [Entity: agent]
                                       |
                                       v
                                  [Thread: agent brain]
                                       |
                                  Agent processes message,
                                  uses chat tools to respond
                                       |
                                       v
                                  [Entity: agent] ---chat_send---> [Entity: human]
                                                                       |
                                                                       v
                                                                  Web UI (SSE push)
```

Messages flow through Chats (conversations between Entities). A Chat between two Entities is automatically created on first contact. Group chats with 3+ entities are also supported.

## Creating an Agent Member (Web UI)

1. Open the Web UI and navigate to the Members page
2. Click "Create" to start a new agent member
3. Fill in the basics:
   - **Name** -- The agent's display name
   - **Description** -- What this agent does
4. Configure the agent:
   - **System Prompt** -- The agent's core instructions (written in the `agent.md` body)
   - **Tools** -- Enable/disable specific tools (file operations, search, web, commands)
   - **Rules** -- Add behavioral rules as individual markdown files
   - **Sub-Agents** -- Define specialized sub-agents with their own tool sets
   - **MCP Servers** -- Connect external tool servers
   - **Skills** -- Enable marketplace skills
5. Set the status to "active" and publish

The backend creates:
- A `MemberRow` in SQLite (`members` table) with a generated `m_` ID
- A file bundle under `~/.leon/members/<id>/`
- An Entity and Thread are created when the agent is first used in a chat

## How Agents Communicate

Agents have five built-in chat tools registered in their tool registry:

### `directory`

Browse all known entities. Returns entity IDs needed for other tools.

```
directory(search="Alice", type="human")
-> - Alice [human] entity_id=m_abc123-1
```

### `chats`

List the agent's active chats with unread counts and last message preview.

```
chats(unread_only=true)
-> - Alice [entity_id: m_abc123-1] (3 unread) -- last: "Can you help me with..."
```

### `chat_read`

Read message history in a chat. Automatically marks messages as read.

```
chat_read(entity_id="m_abc123-1", limit=10)
-> [Alice]: Can you help me with this bug?
   [you]: Sure, let me take a look.
```

### `chat_send`

Send a message. The agent must read unread messages before sending (enforced by the system).

```
chat_send(content="Here's the fix.", entity_id="m_abc123-1")
```

**Signal protocol** controls conversation flow:
- No signal (default) -- "I expect a reply"
- `signal: "yield"` -- "I'm done; reply only if you want to"
- `signal: "close"` -- "Conversation over, do not reply"

### `chat_search`

Search through message history across all chats or within a specific chat.

```
chat_search(query="bug fix", entity_id="m_abc123-1")
```

## How Human-Agent Chat Works

When a human sends a message through the Web UI:

1. The frontend calls `POST /api/chats/{chat_id}/messages` with the message content and the human's entity ID
2. The `ChatService` stores the message and publishes it to the `ChatEventBus` (SSE for real-time UI updates)
3. For each non-sender agent entity in the chat, the delivery system:
   - Checks the **delivery strategy** (contact-level block/mute, chat-level mute, @mention overrides)
   - If delivery is allowed, formats a lightweight notification (no message content -- the agent must `chat_read` to see it)
   - Enqueues the notification into the agent's message queue
   - Wakes the agent's Thread if it was idle (cold-wake)
4. The agent wakes, sees the notification, calls `chat_read` to get the actual messages, processes them, and responds via `chat_send`
5. The agent's response flows back through the same pipeline -- stored, broadcast via SSE, delivered to other participants

### Real-time Updates

The Web UI subscribes to `GET /api/chats/{chat_id}/events` (Server-Sent Events) for live updates:
- `message` events for new messages
- Typing indicators when an agent is processing
- All events are pushed without polling

## Contact and Delivery System

Entities can manage relationships with other entities:

- **Normal** -- Full delivery (default)
- **Muted** -- Messages stored but no notification sent to the agent. @mentions override mute.
- **Blocked** -- Messages are silently dropped for this entity

Chat-level muting is also supported -- mute a specific chat without affecting the contact relationship.

These controls let you manage noisy agents or prevent unwanted interactions without deleting chats.

## API Reference

Key endpoints for the Entity-Chat system:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/entities` | GET | List all chattable entities |
| `/api/members` | GET | List agent members (templates) |
| `/api/chats` | GET | List chats for current user |
| `/api/chats` | POST | Create a new chat (1:1 or group) |
| `/api/chats/{id}/messages` | GET | List messages in a chat |
| `/api/chats/{id}/messages` | POST | Send a message |
| `/api/chats/{id}/read` | POST | Mark chat as read |
| `/api/chats/{id}/events` | GET | SSE stream for real-time events |
| `/api/chats/{id}/mute` | POST | Mute/unmute a chat |
| `/api/entities/contacts` | POST | Set contact relationship (block/mute/normal) |

## Data Storage

The Entity-Chat system uses SQLite databases:

| Database | Tables |
|----------|--------|
| `~/.leon/leon.db` | `members`, `entities`, `accounts` |
| `~/.leon/chat.db` | `chats`, `chat_entities`, `chat_messages`, `contacts` |

Member configuration files live on the filesystem under `~/.leon/members/`. The SQLite tables store relational data (ownership, identity, chat state) while the file bundles store the agent's full configuration.
