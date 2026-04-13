# Database Refactor Meeting: Distilled Decisions

Date: 2026-04-14

Source transcript:

- `/Users/lexicalmathical/Downloads/43876540-3be8-4c8a-b5c5-fa1e496057f0.txt`

This file is the post-discussion summary. Prefer this over raw early transcript fragments when the discussion contradicts itself.

## Refactor Shape

This database refactor is an aggressive ontology rewrite, not a small compatibility migration.

Checkpoint rule:

- keep each schema move narrow
- bring uncertain concepts back to Ledger before DDL or runtime routing
- do not preserve old concepts only because current tables exist
- do not hide mismatches with application fallbacks/defaults

## Sandbox / Container / Workspace

Terminology rule:

- do not use `environment` as a product/schema concept
- transcript references to environment should be interpreted as the later, clearer `sandbox` concept
- use sandbox as the primary name unless a later checkpoint specifically needs a lower-level container implementation detail

The core runtime relation is thread to sandbox/container execution.

Do not model the core path as:

```text
thread -> workspace -> device
```

Correct interpretation:

- thread needs a sandbox/container execution target directly
- workspace is a thin working-directory or project context inside one sandbox
- workspace is useful only when a real runtime/API needs cwd/project selection
- workspace has no direct old-table mapping
- device may also be a new identifier-like concept and should not be forced into the first agent thread slice

`sandbox_type` is current runtime contract state. It may later be replaced by a stronger sandbox/container relation, but it should not be replaced by a fake default or hidden fallback.

## Sandbox Template

`recipe` is not a final target concept.

Final interpretation:

- the old recipe concept is deleted as a standalone name
- the surviving product/schema concept is `Sandbox Template`
- `Sandbox Template` belongs to sandbox creation
- it should not be buried under workspace unless a later checkpoint proves workspace-specific configuration is needed

Working direction:

- sandbox template/config describes preinstalled CLI/SDK/tooling and resource shape
- current naming should follow the target design once Ledger confirms the exact table name
- avoid `library_recipes` as the final name

## Terminal / Process

Persistent terminal tables are not automatically justified.

Working interpretation:

- the old terminal layer is removed from the target path
- chat session is also removed from the target path
- execution should align with the Claude Code style: direct subprocess execution rather than persistent PTY modeling
- running state can be owned by the sandbox/container runtime or backend memory
- completed output/result should be stored in product records such as thread/message/run result surfaces
- if a running process abstraction is needed, design it explicitly; do not keep old terminal tables by inertia

## Mount / Volume / File Transfer

Mount and volume are the same conceptual layer for this refactor. They should be removed together, not split into two concepts.

File upload/download should become a unified sandbox upload/download interface.

Working direction:

- do not preserve `sandbox_volumes`
- do not introduce a separate mount table as a replacement for volume
- route file transfer through sandbox/container APIs
- if shared storage becomes a paid/advanced product feature later, it needs a separate checkpoint and product justification

## Session / Chat Session

Session/chat_session is not part of the target base schema.

If current code still depends on it, that is a cleanup checkpoint, not a reason to keep the table.

## Schedules / Tasks

`agent.thread_tasks` and schedules are separate work.

Current 02A scope:

- `agent.threads`
- `agent.thread_tasks`

Do not mix `cron_jobs`, `panel_tasks`, or schedule execution semantics into the 02A thread task landing.

## Testing / Product Proof

Backend API YATU can be used while DB work is in progress, but closure needs product-level proof after routing:

- login
- thread list
- task create/list/get/update through high-level APIs or the real task tool surface
- no direct helper-only proof as closure
