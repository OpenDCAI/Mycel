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
        mode_label = (
            "Sandbox (isolated local container)"
            if sandbox_name == "docker"
            else "Sandbox (isolated cloud environment)"
        )
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
    rules: list[str] = []

    # Rule 1: Environment-specific
    if is_sandbox:
        if sandbox_name == "docker":
            location_rule = "All file and command operations run in a local Docker container, NOT on the user's host filesystem."
        else:
            location_rule = "All file and command operations run in a remote sandbox, NOT on the user's local machine."
        rules.append(f"1. **Sandbox Environment**: {location_rule} The sandbox is an isolated Linux environment.")
    else:
        rules.append("1. **Workspace**: File operations are restricted to: " + workspace_root)

    # Rule 2: Absolute paths
    rules.append(f"""2. **Absolute Paths**: All file paths must be absolute paths.
   - ✅ Correct: `{working_dir}/project/test.py`
   - ❌ Wrong: `test.py` or `./test.py`""")

    # Rule 3: Security
    if is_sandbox:
        rules.append("3. **Security**: The sandbox is isolated. You can install packages, run any commands, and modify files freely.")
    else:
        rules.append("3. **Security**: Dangerous commands are blocked. All operations are logged.")

    # Rule 4: Tool priority
    rules.append(
        """4. **Tool Priority**: When a built-in tool and an MCP tool (`mcp__*`) have the same functionality, use the built-in tool."""
    )

    # Rule 5: Dedicated tools over shell
    rules.append("""5. **Use Dedicated Tools Instead of Shell Commands**: Do NOT use `Bash` for tasks that have dedicated tools:
   - File search → use `Grep` (NOT `rg`, `grep`, or `find` via Bash)
   - File listing → use `Glob` (NOT `find` or `ls` via Bash)
   - File reading → use `Read` (NOT `cat`, `head`, `tail` via Bash)
   - File editing → use `Edit` (NOT `sed` or `awk` via Bash)
   - Reserve `Bash` for: git, package managers, build tools, tests, and other system operations.""")

    # Rule 6: Background task description
    rules.append("""6. **Background Task Description**: When using `Bash` or `Agent` with `run_in_background: true`, always include a clear `description` parameter.
   - The description is shown to the user in the background task indicator.
   - Keep it concise (5–10 words), action-oriented, e.g. "Run test suite", "Analyze API codebase".
   - Without a description, the raw command or agent name is shown, which is hard to read.""")

    # Rule 7: Deferred tools
    rules.append("7. **Deferred Tools**: Some tools are available but not shown by default. Use `tool_search` to discover them by name or keyword.")

    return "\n\n".join(rules)


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
