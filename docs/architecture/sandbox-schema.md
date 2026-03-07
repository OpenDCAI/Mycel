# Sandbox Database Schema

**Date:** 2026-03-07
**Purpose:** Document all tables used by sandbox domain layer

---

## Overview

The sandbox layer uses 8 tables across 4 entity groups:

1. **Leases** - Durable compute handles (3 tables)
2. **Terminals** - Terminal state and pointers (2 tables)
3. **Sessions** - Chat sessions and commands (3 tables)
4. **Events** - Provider events (1 table)

---

## Lease Tables

### sandbox_leases

Durable lease state with lifecycle tracking.

```sql
CREATE TABLE IF NOT EXISTS sandbox_leases (
    lease_id TEXT PRIMARY KEY,
    provider_name TEXT NOT NULL,
    workspace_key TEXT,
    current_instance_id TEXT,
    instance_created_at TIMESTAMP,
    desired_state TEXT NOT NULL DEFAULT 'running',
    observed_state TEXT NOT NULL DEFAULT 'detached',
    instance_status TEXT NOT NULL DEFAULT 'detached',
    version INTEGER NOT NULL DEFAULT 0,
    observed_at TIMESTAMP,
    last_error TEXT,
    needs_refresh INTEGER NOT NULL DEFAULT 0,
    refresh_hint_at TIMESTAMP,
    status TEXT DEFAULT 'active',
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
)
```

**Source:** `sandbox/lease.py:770`

### sandbox_instances

Ephemeral instance records.

```sql
CREATE TABLE IF NOT EXISTS sandbox_instances (
    instance_id TEXT PRIMARY KEY,
    lease_id TEXT NOT NULL,
    provider_session_id TEXT NOT NULL,
    status TEXT DEFAULT 'running',
    created_at TIMESTAMP NOT NULL,
    last_seen_at TIMESTAMP NOT NULL
)
```

**Source:** `sandbox/lease.py:792`

### lease_events

Lease lifecycle event log.

```sql
CREATE TABLE IF NOT EXISTS lease_events (
    event_id TEXT PRIMARY KEY,
    lease_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    source TEXT NOT NULL,
    payload_json TEXT,
    error TEXT,
    created_at TIMESTAMP NOT NULL
)
```

**Index:** `idx_lease_events_lease_created ON lease_events(lease_id, created_at DESC)`

**Source:** `sandbox/lease.py:804`

---

## Terminal Tables

### abstract_terminals

Durable terminal state snapshots.

```sql
CREATE TABLE IF NOT EXISTS abstract_terminals (
    terminal_id TEXT PRIMARY KEY,
    thread_id TEXT NOT NULL,
    lease_id TEXT NOT NULL,
    cwd TEXT NOT NULL,
    env_delta_json TEXT DEFAULT '{}',
    state_version INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```

**Index:** `idx_abstract_terminals_thread_created ON abstract_terminals(thread_id, created_at DESC)`

**Source:** `sandbox/terminal.py:185`

### thread_terminal_pointers

Thread-to-terminal mapping.

```sql
CREATE TABLE IF NOT EXISTS thread_terminal_pointers (
    thread_id TEXT PRIMARY KEY,
    active_terminal_id TEXT NOT NULL,
    default_terminal_id TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (active_terminal_id) REFERENCES abstract_terminals(terminal_id),
    FOREIGN KEY (default_terminal_id) REFERENCES abstract_terminals(terminal_id)
)
```

**Source:** `sandbox/terminal.py:199`

---

## Session Tables

### chat_sessions

Chat session lifecycle and policy.

```sql
CREATE TABLE IF NOT EXISTS chat_sessions (
    chat_session_id TEXT PRIMARY KEY,
    thread_id TEXT NOT NULL,
    terminal_id TEXT NOT NULL,
    lease_id TEXT NOT NULL,
    runtime_id TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    idle_ttl_sec INTEGER NOT NULL,
    max_duration_sec INTEGER NOT NULL,
    budget_json TEXT,
    started_at TIMESTAMP NOT NULL,
    last_active_at TIMESTAMP NOT NULL,
    ended_at TIMESTAMP,
    close_reason TEXT,
    FOREIGN KEY (terminal_id) REFERENCES abstract_terminals(terminal_id),
    FOREIGN KEY (lease_id) REFERENCES sandbox_leases(lease_id)
)
```

**Source:** `sandbox/chat_session.py:198`

### terminal_commands

Command execution records.

```sql
CREATE TABLE IF NOT EXISTS terminal_commands (
    command_id TEXT PRIMARY KEY,
    terminal_id TEXT NOT NULL,
    chat_session_id TEXT,
    command_line TEXT NOT NULL,
    cwd TEXT NOT NULL,
    status TEXT NOT NULL,
    stdout TEXT DEFAULT '',
    stderr TEXT DEFAULT '',
    exit_code INTEGER,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    finished_at TIMESTAMP,
    FOREIGN KEY (terminal_id) REFERENCES abstract_terminals(terminal_id),
    FOREIGN KEY (chat_session_id) REFERENCES chat_sessions(chat_session_id)
)
```

**Source:** `sandbox/chat_session.py:225`

### terminal_command_chunks

Streaming command output chunks.

```sql
CREATE TABLE IF NOT EXISTS terminal_command_chunks (
    chunk_id INTEGER PRIMARY KEY AUTOINCREMENT,
    command_id TEXT NOT NULL,
    stream TEXT NOT NULL CHECK (stream IN ('stdout', 'stderr')),
    content TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    FOREIGN KEY (command_id) REFERENCES terminal_commands(command_id)
)
```

**Index:** `idx_terminal_command_chunks_command_order ON terminal_command_chunks(command_id, chunk_id)`

**Source:** `sandbox/chat_session.py:251`

---

## Event Tables

### provider_events

Provider webhook/event log.

```sql
CREATE TABLE IF NOT EXISTS provider_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider_name TEXT NOT NULL,
    instance_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload_json TEXT,
    matched_lease_id TEXT,
    created_at TIMESTAMP NOT NULL
)
```

**Index:** `idx_provider_events_created ON provider_events(created_at DESC)`

**Source:** `sandbox/provider_events.py:30`

---

## Entity Relationships

```
Thread
  ├─> thread_terminal_pointers (1:1)
  │     └─> abstract_terminals (N:1)
  │           └─> sandbox_leases (N:1)
  └─> chat_sessions (1:N)
        ├─> abstract_terminals (N:1)
        ├─> sandbox_leases (N:1)
        └─> terminal_commands (1:N)
              └─> terminal_command_chunks (1:N)

SandboxLease
  ├─> sandbox_instances (1:N)
  └─> lease_events (1:N)

Provider
  └─> provider_events (1:N)
```

---

## Notes

- **No tables in:** runtime.py, manager.py, capability.py (these files have SQL operations but use existing tables)
- **Foreign keys:** Only enforced in terminal_pointers, chat_sessions, terminal_commands, terminal_command_chunks
- **Indexes:** 4 total (lease_events, abstract_terminals, terminal_command_chunks, provider_events)
- **Timestamps:** Mix of CURRENT_TIMESTAMP defaults and explicit NOT NULL
