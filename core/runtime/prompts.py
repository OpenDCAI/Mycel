"""System prompt builders — pure functions, no agent state.

Extracted from LeonAgent so agent.py stays lean.

Middleware Stack
- MemoryMiddleware: trims/compacts conversation context before model calls.
- MonitorMiddleware: aggregates runtime metrics and observes model execution.
- PromptCachingMiddleware: enables Anthropic prompt caching for eligible requests.
- SteeringMiddleware: drains queued messages and injects them before the next model call.
- SpillBufferMiddleware: spills oversized tool outputs to disk and replaces them with previews.
"""

from __future__ import annotations

from typing import NamedTuple


class RuleSpec(NamedTuple):
    title: str
    body: str
    details: tuple[str, ...] = ()


def _render_rule(index: int, rule: RuleSpec) -> str:
    rendered = f"{index}. **{rule.title}**: {rule.body}"
    if not rule.details:
        return rendered
    return rendered + "\n" + "\n".join(f"   - {detail}" for detail in rule.details)


def _build_core_rules(*, is_sandbox: bool, sandbox_name: str, workspace_root: str, working_dir: str) -> list[RuleSpec]:
    rules: list[RuleSpec] = []
    if is_sandbox:
        if sandbox_name == "docker":
            location_rule = "All file and command operations run in a local Docker container, NOT on the user's host filesystem."
        else:
            location_rule = "All file and command operations run in a remote sandbox, NOT on the user's local machine."
        rules.append(RuleSpec("Sandbox Environment", f"{location_rule} The sandbox is an isolated Linux environment."))
    else:
        rules.append(RuleSpec("Workspace", "File operations are restricted to: " + workspace_root))

    rules.append(
        RuleSpec(
            "Absolute Paths",
            "All file paths must be absolute paths.",
            (
                f"Correct: `{working_dir}/project/test.py`",
                "Wrong: `test.py` or `./test.py`",
            ),
        )
    )

    if is_sandbox:
        security = "The sandbox is isolated. You can install packages, run any commands, and modify files freely."
    else:
        security = "Dangerous commands are blocked. All operations are logged."
    rules.append(RuleSpec("Security", security))
    return rules


def _build_risk_rules() -> list[RuleSpec]:
    return [
        RuleSpec(
            "Risky Actions",
            "Ask before destructive, hard-to-reverse, or shared-state actions.",
            (
                "Examples: deleting files, force-pushing, dropping tables, killing unfamiliar processes, modifying shared infrastructure.",
                "If you see unexpected state, investigate before deleting or overwriting it.",
            ),
        ),
        RuleSpec(
            "No URL Guessing",
            "Do not guess URLs unless the user provided them or you are confident they are directly relevant to programming help.",
        ),
        RuleSpec(
            "Minimal Change",
            "Do not add features, refactor code, or make speculative abstractions beyond what the task requires.",
            (
                "Don't create helpers, utilities, or abstractions for one-time operations.",
                "Don't add error handling, fallbacks, or validation for scenarios that can't happen.",
            ),
        ),
    ]


def _build_tool_preference_rules() -> list[RuleSpec]:
    return [
        RuleSpec(
            "Tool Priority",
            "When a built-in tool and an MCP tool (`mcp__*`) have the same functionality, use the built-in tool.",
        ),
        RuleSpec(
            "Tool Preference",
            "Prefer dedicated tools over `Bash` when a built-in tool already matches the job.",
            (
                "Use `Read` instead of `cat`, `head`, or `tail`.",
                "Use `Edit` instead of shell text-munging for file edits.",
                "Use `Write` instead of heredoc or echo redirection for file creation.",
                "Use `Glob`/`Grep` for file discovery and content search before falling back to `Bash`.",
            ),
        ),
    ]


def _build_interaction_rules() -> list[RuleSpec]:
    return []


def _build_rule_specs(
    *,
    is_sandbox: bool,
    sandbox_name: str,
    workspace_root: str,
    working_dir: str,
) -> list[RuleSpec]:
    rules: list[RuleSpec] = []
    rules.extend(
        _build_core_rules(
            is_sandbox=is_sandbox,
            sandbox_name=sandbox_name,
            workspace_root=workspace_root,
            working_dir=working_dir,
        )
    )
    rules.extend(_build_risk_rules())
    rules.extend(_build_tool_preference_rules())
    rules.extend(_build_interaction_rules())
    return rules


def build_context_section(
    *,
    sandbox_name: str,
    sandbox_env_label: str = "",
    sandbox_working_dir: str = "",
    workspace_root: str = "",
    os_name: str = "",
    shell_name: str = "",
) -> str:
    if sandbox_name != "local":
        mode_label = "Sandbox (isolated local container)" if sandbox_name == "docker" else "Sandbox (isolated cloud environment)"
        return f"""- Environment: {sandbox_env_label}
- Working Directory: {sandbox_working_dir}
- Mode: {mode_label}"""
    return f"""- Workspace: `{workspace_root}`
- OS: {os_name}
- Shell: {shell_name}
- Mode: Local"""


def build_rules_section(
    *,
    is_sandbox: bool,
    sandbox_name: str = "",
    working_dir: str,
    workspace_root: str,
) -> str:
    rule_specs = _build_rule_specs(
        is_sandbox=is_sandbox,
        sandbox_name=sandbox_name,
        workspace_root=workspace_root,
        working_dir=working_dir,
    )
    return "\n\n".join(_render_rule(index, rule) for index, rule in enumerate(rule_specs, start=1))


def build_base_prompt(context: str, rules: str) -> str:
    return f"""You are a highly capable AI assistant with access to file and system tools.

**Context:**
{context}

**Important Rules:**

{rules}
"""


_AGENT_TOOL_SECTION = """
**Sub-agent Types:**
- `explore`: Read-only codebase exploration (Grep, Glob, Read only)
- `plan`: Architecture design and planning (read-only tools)
- `bash`: Shell command execution (Bash + read tools)
- `general`: Full tool access for independent multi-step tasks
"""


def build_common_sections(skills_enabled: bool) -> str:
    return _AGENT_TOOL_SECTION
