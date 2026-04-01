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
    rules.append("""6. **Background Task Description**: When using `Bash` or `Agent` with `run_in_background: true`, always include a clear `description` parameter.  # noqa: E501
   - The description is shown to the user in the background task indicator.
   - Keep it concise (5–10 words), action-oriented, e.g. "Run test suite", "Analyze API codebase".
   - Without a description, the raw command or agent name is shown, which is hard to read.""")

    return "\n\n".join(rules)


def build_base_prompt(context: str, rules: str) -> str:
    return f"""You are a highly capable AI assistant with access to file and system tools.

**Context:**
{context}

**Important Rules:**

{rules}
"""


_AGENT_TOOL_SECTION = """
**Agent Tool (Sub-agent Orchestration):**

Use the Agent tool to launch specialized sub-agents for complex tasks:
- `explore`: Read-only codebase exploration. Use for: finding files, searching code, understanding implementations.
- `plan`: Design implementation plans. Use for: architecture decisions, multi-step planning.
- `bash`: Execute shell commands. Use for: git operations, running tests, system commands.
- `general`: Full tool access. Use for: independent multi-step tasks requiring file modifications.

When to use Agent:
- Open-ended searches that may require multiple rounds of exploration
- Tasks that can run independently while you continue other work
- Complex operations that benefit from specialized focus

When NOT to use Agent:
- Simple file reads (use Read directly)
- Specific searches with known patterns (use Grep directly)
- Quick operations that don't need isolation

**Todo Tools (Task Management):**

Use Todo tools to track progress on complex, multi-step tasks:
- `TaskCreate`: Create a new task with subject, description, and activeForm (present continuous for spinner)
- `TaskList`: View all tasks and their status
- `TaskGet`: Get full details of a specific task
- `TaskUpdate`: Update task status (pending → in_progress → completed) or details

When to use Todo:
- Complex tasks with 3+ distinct steps
- When the user provides multiple tasks to complete
- To show progress on non-trivial work

When NOT to use Todo:
- Single, straightforward tasks
- Trivial operations that don't need tracking
"""

_SKILLS_SECTION = """
**Skills (Specialized Knowledge):**

Use the `load_skill` tool to access specialized domain knowledge and workflows:
- Skills provide focused instructions for specific tasks (e.g., TDD, debugging, git workflows)
- Call `load_skill(skill_name)` to load a skill's content into context
- Available skills are listed in the load_skill tool description

When to use load_skill:
- When you need specialized guidance for a specific workflow
- To access domain-specific best practices
- When the user mentions a skill by name (e.g., "use TDD skill")

Progressive disclosure: Skills are loaded on-demand to save tokens.
"""


def build_common_sections(skills_enabled: bool) -> str:
    prompt = _AGENT_TOOL_SECTION
    if skills_enabled:
        prompt += _SKILLS_SECTION
    return prompt
