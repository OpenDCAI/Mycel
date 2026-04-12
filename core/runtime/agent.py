"""
Leon - AI Coding Agent with Middleware Architecture

Middleware stack (outer → inner):
  SpillBuffer → Monitor → PromptCaching → Memory → Steering → ToolRunner

Tools are registered via Services into ToolRegistry:
- FileSystemService: Read, Write, Edit, list_dir
- SearchService: Grep, Glob
- CommandService: Bash (with hooks)
- WebService: WebSearch, WebFetch
- SkillsService: load_skill (dynamic schema)
- TaskService: TaskCreate/Update/List/Get (deferred)
- AgentService: Agent, TaskOutput, TaskStop
- ToolSearchService: tool_search

All paths must be absolute. Full security mechanisms and audit logging.
"""

import asyncio
import concurrent.futures
import inspect
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from langchain.chat_models import init_chat_model
from langchain_core.messages import SystemMessage

# Load .env file
_env_file = Path(__file__).parent / ".env"
if _env_file.exists():
    for line in _env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ[key] = value

from config import LeonSettings  # noqa: E402
from config.loader import AgentLoader, load_bundle_from_repo  # noqa: E402
from config.models_loader import ModelsLoader  # noqa: E402
from config.models_schema import ModelsConfig  # noqa: E402
from config.observation_loader import ObservationLoader  # noqa: E402
from config.observation_schema import ObservationConfig  # noqa: E402

# Multi-agent services
from core.agents.registry import AgentRegistry  # noqa: E402
from core.agents.service import AgentService  # noqa: E402
from core.model_params import normalize_model_kwargs  # noqa: E402

# Import file operation recorder for time travel
from core.operations import get_recorder  # noqa: E402

# New architecture: ToolRegistry + ToolRunner + Services
from core.runtime.cleanup import CleanupRegistry  # noqa: E402
from core.runtime.loop import QueryLoop  # noqa: E402
from core.runtime.middleware.mcp_instructions import McpInstructionsDeltaMiddleware  # noqa: E402
from core.runtime.middleware.memory import MemoryMiddleware  # noqa: E402
from core.runtime.middleware.monitor import MonitorMiddleware, apply_usage_patches  # noqa: E402
from core.runtime.middleware.prompt_caching import PromptCachingMiddleware  # noqa: E402
from core.runtime.middleware.queue import MessageQueueManager, SteeringMiddleware  # noqa: E402

# Middleware imports (migrated paths)
from core.runtime.middleware.spill_buffer import SpillBufferMiddleware  # noqa: E402
from core.runtime.registry import ToolEntry, ToolMode, ToolRegistry, make_tool_schema  # noqa: E402
from core.runtime.runner import ToolRunner  # noqa: E402
from core.runtime.state import AppState, BootstrapConfig  # noqa: E402
from core.runtime.validator import ToolValidator  # noqa: E402

# Hooks (used by Services)
from core.tools.command.hooks.dangerous_commands import DangerousCommandsHook  # noqa: E402
from core.tools.command.hooks.file_access_logger import FileAccessLoggerHook  # noqa: E402
from core.tools.command.hooks.file_permission import FilePermissionHook  # noqa: E402
from core.tools.command.service import CommandService  # noqa: E402
from core.tools.filesystem.service import FileSystemService  # noqa: E402
from core.tools.mcp_resources.service import McpResourceToolService  # noqa: E402
from core.tools.search.service import SearchService  # noqa: E402
from core.tools.skills.service import SkillsService  # noqa: E402
from core.tools.task.service import TaskService  # noqa: E402
from core.tools.tool_search.service import ToolSearchService  # noqa: E402

# Multi-agent team coordination
# from core.agents.teams.service import TeamService  # @@@teams-removed - module doesn't exist
from core.tools.web.service import WebService  # noqa: E402
from storage.container import StorageContainer  # noqa: E402

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from sandbox import Sandbox

# @@@langchain-anthropic-streaming-usage-regression
apply_usage_patches()


def _make_mcp_tool_entry(tool) -> ToolEntry:
    schema_model = getattr(tool, "tool_call_schema", None)
    if schema_model is not None and hasattr(schema_model, "model_json_schema"):
        parameters = schema_model.model_json_schema()
    else:
        parameters = {
            "type": "object",
            "properties": getattr(tool, "args", {}) or {},
        }

    async def mcp_handler(**kwargs):
        if hasattr(tool, "ainvoke"):
            return await tool.ainvoke(kwargs)
        return await asyncio.to_thread(tool.invoke, kwargs)

    return ToolEntry(
        name=tool.name,
        mode=ToolMode.INLINE,
        schema=make_tool_schema(
            name=tool.name,
            description=getattr(tool, "description", "") or tool.name,
            properties={},
            parameter_overrides=parameters,
        ),
        handler=mcp_handler,
        source="mcp",
    )


class LeonAgent:
    """
    Leon Agent - AI Coding Assistant

    Features:
    - Pure Middleware architecture
    - Absolute path enforcement
    - Full security (permission control, command interception, audit logging)

    Tools:
    1. File operations: Read, Write, Edit, list_dir
    2. Search: Grep, Glob
    3. Command execution: Bash (via CommandService)
    """

    def __init__(
        self,
        model_name: str | None = None,
        api_key: str | None = None,
        workspace_root: str | Path | None = None,
        *,
        agent: str | None = None,
        bundle_dir: str | Path | None = None,
        agent_config_id: str | None = None,
        agent_config_repo: Any = None,
        allowed_file_extensions: list[str] | None = None,
        block_dangerous_commands: bool | None = None,
        block_network_commands: bool | None = None,
        enable_audit_log: bool | None = None,
        enable_web_tools: bool | None = None,
        tavily_api_key: str | None = None,
        exa_api_key: str | None = None,
        firecrawl_api_key: str | None = None,
        jina_api_key: str | None = None,
        sandbox: Any = None,
        storage_container: StorageContainer | None = None,
        thread_repo: Any = None,
        user_repo: Any = None,
        queue_manager: MessageQueueManager | None = None,
        chat_repos: dict | None = None,
        web_app: Any = None,
        extra_allowed_paths: list[str] | None = None,
        extra_blocked_tools: set[str] | None = None,
        allowed_tools: set[str] | None = None,
        models_config_override: dict[str, Any] | None = None,
        memory_config_override: dict[str, Any] | None = None,
        permission_resolver_scope: str = "none",
        verbose: bool = False,
    ):
        """
        Initialize Leon Agent

        Args:
            model_name: Model name (supports leon:mini/medium/large/max virtual names)
            api_key: API key (defaults to environment variables)
            workspace_root: Workspace directory (all operations restricted to this directory)
            agent: Task Agent name to run as (e.g., "bash", "explore", "general", "plan")
            allowed_file_extensions: Allowed file extensions (None means all allowed)
            block_dangerous_commands: Whether to block dangerous commands
            block_network_commands: Whether to block network commands
            enable_audit_log: Whether to enable audit logging
            enable_web_tools: Whether to enable web search and content fetching tools
            sandbox: Sandbox instance, name string, or None for local
            thread_repo: Optional thread metadata repo for backend-integrated subagent registration
            user_repo: Optional user repo for backend-integrated subagent registration
            queue_manager: Shared MessageQueueManager instance (created if not provided)
            permission_resolver_scope: Permission request surface for this agent ("none" or "thread")
            verbose: Whether to output detailed logs (default False)
        """
        runtime_storage = storage_container

        self.agent_id: str | None = None
        self.verbose = verbose
        self.extra_allowed_paths = extra_allowed_paths
        self.queue_manager = queue_manager or (
            MessageQueueManager(repo=runtime_storage.queue_repo()) if runtime_storage is not None else MessageQueueManager()
        )
        self._chat_repos: dict | None = chat_repos
        self._thread_repo = thread_repo
        self._user_repo = user_repo
        self._web_app = web_app
        self._session_started = False
        self._session_ended = False
        self._closing = False
        self._closed = False
        requested_sandbox_name = sandbox if isinstance(sandbox, str) else getattr(sandbox, "name", None)
        self._explicit_model_name = model_name is not None

        # New config system mode
        self.config, self.models_config = self._load_config(
            agent_name=agent,
            bundle_dir=bundle_dir,
            agent_config_id=agent_config_id,
            agent_config_repo=agent_config_repo,
            workspace_root=workspace_root,
            sandbox_name=requested_sandbox_name,
            model_name=model_name,
            api_key=api_key,
            allowed_file_extensions=allowed_file_extensions,
            block_dangerous_commands=block_dangerous_commands,
            block_network_commands=block_network_commands,
            enable_audit_log=enable_audit_log,
            enable_web_tools=enable_web_tools,
            models_config_override=models_config_override,
            memory_config_override=memory_config_override,
        )
        # Load observation config (langfuse / langsmith)
        self._observation_config = ObservationLoader(workspace_root=workspace_root).load()
        # Resolve virtual model name
        active_model = self.models_config.active.model if self.models_config.active else model_name
        if not active_model:
            from config.schema import DEFAULT_MODEL  # noqa: E402

            active_model = DEFAULT_MODEL
        # Agent frontmatter model applies only when the caller did not explicitly
        # request a model at construction time.
        if not self._explicit_model_name and hasattr(self, "_agent_override") and self._agent_override and self._agent_override.model:
            active_model = self._agent_override.model
        resolved_model, model_overrides = self.models_config.resolve_model(active_model)
        self.model_name = resolved_model
        self._model_overrides = model_overrides

        # Resolve API key (prefer resolved provider from mapping)
        provider_name = self._resolve_provider_name(resolved_model, model_overrides)
        self._explicit_api_key = api_key is not None
        self.api_key = api_key or self.models_config.resolve_api_key(provider_name)

        if not self.api_key:
            raise ValueError(
                "API key must be set via:\n"
                "  - OPENAI_API_KEY environment variable (recommended for proxy)\n"
                "  - ANTHROPIC_API_KEY environment variable\n"
                "  - api_key parameter\n"
                "  - models.json providers section"
            )

        # Initialize workspace and configuration
        self.workspace_root = self._resolve_workspace_root()
        self._init_config_attributes()
        self.storage_container: StorageContainer | None = runtime_storage
        self._sandbox = self._init_sandbox(sandbox)

        # Override workspace_root for sandbox mode
        if self._sandbox.name != "local":
            self.workspace_root = Path(self._sandbox.working_dir)
        else:
            self.workspace_root.mkdir(parents=True, exist_ok=True)

        # Initialize model
        self.model = self._create_model()

        # Store current model config for per-request override via configurable_fields
        model_kwargs = self._build_model_kwargs()
        self._current_model_config = {
            "model": self.model_name,
            "model_provider": model_kwargs.get("model_provider"),
            "api_key": self.api_key,
            "base_url": model_kwargs.get("base_url"),
        }

        # Initialize checkpointer and MCP tools
        self.checkpointer = None
        _conn, mcp_tools = self._init_async_components()

        # If in async context (running loop detected), _init_async_components
        # skips init and returns (None, []). Distinguish from Postgres path
        # which also returns conn=None but DID initialize successfully.
        self._needs_async_init = self.checkpointer is None

        # Set checkpointer to None if in async context (will be initialized later)
        if self._needs_async_init:
            self.checkpointer = None

        # Initialize ToolRegistry and Services (new architecture)
        blocked = self._get_agent_blocked_tools()
        if extra_blocked_tools:
            blocked = blocked | extra_blocked_tools
        self._tool_registry = ToolRegistry(
            blocked_tools=blocked,
            allowed_tools=allowed_tools,
        )
        self._init_services()
        self._register_mcp_tools(mcp_tools)

        # Build middleware stack
        middleware = self._build_middleware_stack()

        # Ensure the bound model still sees at least one BaseTool-compatible entry.
        if not mcp_tools and not self._has_middleware_tools(middleware):
            mcp_tools = [self._create_placeholder_tool()]

        self._system_prompt_section_cache: dict[str, str] = {}
        self.system_prompt = self._compose_system_prompt()

        # Build BootstrapConfig for sub-agent forking
        self._bootstrap = BootstrapConfig(
            workspace_root=self.workspace_root,
            original_cwd=Path.cwd(),
            project_root=self.workspace_root,
            cwd=self.workspace_root,
            model_name=self.model_name,
            api_key=self.api_key,
            sandbox_type=self._sandbox.name,
            permission_resolver_scope=permission_resolver_scope,
            block_dangerous_commands=self.block_dangerous_commands,
            block_network_commands=self.block_network_commands,
            enable_audit_log=self.enable_audit_log,
            enable_web_tools=self.enable_web_tools,
            allowed_file_extensions=self.allowed_file_extensions,
            extra_allowed_paths=self.extra_allowed_paths,
            model_provider=self._current_model_config.get("model_provider"),
            base_url=self._current_model_config.get("base_url"),
        )
        self._app_state = AppState()
        self.app_state = self._app_state
        # Inject bootstrap into AgentService so sub-agents can fork from it
        if hasattr(self, "_agent_service"):
            self._agent_service._parent_bootstrap = self._bootstrap

        # Create agent via QueryLoop (replaces LangGraph create_agent)
        self.agent = QueryLoop(
            model=self.model,
            system_prompt=SystemMessage(content=[{"type": "text", "text": self.system_prompt}]),
            middleware=middleware,
            checkpointer=self.checkpointer,
            registry=self._tool_registry,
            app_state=self._app_state,
            runtime=self._monitor_middleware.runtime,
            bootstrap=self._bootstrap,
        )

        # Get runtime from MonitorMiddleware
        self.runtime = self._monitor_middleware.runtime

        # Inject runtime into MemoryMiddleware and SteeringMiddleware
        if hasattr(self, "_memory_middleware"):
            self._memory_middleware.set_runtime(self.runtime)
        if hasattr(self, "_steering_middleware"):
            self._steering_middleware._agent_runtime = self.runtime
            self._memory_middleware.set_model(self.model, self._current_model_config)

        if self.verbose:
            print("[LeonAgent] Initialized successfully")
            print(f"[LeonAgent] Workspace: {self.workspace_root}")
            print(f"[LeonAgent] Audit log: {self.enable_audit_log}")
            if self.checkpointer is None:
                print("[LeonAgent] Note: Async components need initialization via ainit()")

        # Wire CleanupRegistry for priority-ordered resource teardown
        self._cleanup_registry = CleanupRegistry()
        self._cleanup_registry.register(self._cleanup_sandbox, priority=2)
        self._cleanup_registry.register(self._mark_terminated, priority=3)
        self._cleanup_registry.register(self._cleanup_mcp_client, priority=4)
        self._cleanup_registry.register(self._cleanup_sqlite_connection, priority=5)

        # Mark agent as ready (checkpointer is None when async init still pending)
        if self.checkpointer is not None:
            self._monitor_middleware.mark_ready()

    @property
    def sandbox(self) -> "Sandbox":
        # @@@public-sandbox-surface - integration callers already drive fs/shell through
        # agent.sandbox; make that contract explicit instead of relying on a private attr.
        return self._sandbox

    def apply_forked_child_context(
        self,
        bootstrap: BootstrapConfig,
        *,
        tool_context: Any | None = None,
    ) -> None:
        # @@@subagent-fork-wiring
        # AgentService should not reach through LeonAgent and mutate QueryLoop
        # internals directly. Keep the child bootstrap + abort-controller wiring
        # behind one explicit LeonAgent seam.
        self._bootstrap = bootstrap
        self.agent._bootstrap = bootstrap
        if hasattr(self, "_agent_service"):
            self._agent_service._parent_bootstrap = bootstrap
            if tool_context is not None:
                self._agent_service._parent_tool_context = tool_context
        if tool_context is not None:
            self.agent._tool_abort_controller = tool_context.abort_controller

    async def ainit(self):
        """Complete async initialization (call this if initialized in async context).

        Example:
            agent = LeonAgent(sandbox=sandbox)
            await agent.ainit()
        """
        if self.checkpointer is None:
            # Initialize async components
            await self._init_checkpointer()
            _mcp_tools = await self._init_mcp_tools()
            self._register_mcp_tools(_mcp_tools)

            # Update agent with checkpointer
            self.agent.checkpointer = self.checkpointer
            if hasattr(self, "_memory_middleware"):
                # @@@late-checkpointer-fanout - async bringup creates the saver after
                # middleware construction, so QueryLoop and MemoryMiddleware must be
                # rewired together or rebuild/persistence surfaces drift apart.
                self._memory_middleware.checkpointer = self.checkpointer

            self._monitor_middleware.mark_ready()

            if self.verbose:
                print("[LeonAgent] Async initialization completed")

        if not self._session_started:
            await self._run_session_hooks("SessionStart")
            self._session_started = True

    def _init_async_components(self) -> tuple[Any, list]:
        """Initialize async components (checkpointer and MCP tools).

        Note: We don't use asyncio.run() here because it closes the event loop,
        which causes issues with aiosqlite cleanup. Instead, we create a persistent
        event loop that will be cleaned up when the process exits.
        """
        import asyncio

        try:
            # Check if we're already in an async context
            loop = asyncio.get_running_loop()
            return None, []
        except RuntimeError:
            # Create a new event loop and keep it running
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            # Store the loop for later use
            self._event_loop = loop

            # Initialize components
            loop.run_until_complete(self._init_checkpointer())
            mcp_tools = loop.run_until_complete(self._init_mcp_tools())

            return None, mcp_tools

    def _has_middleware_tools(self, middleware: list) -> bool:
        """Check if any middleware has BaseTool instances."""
        return any(getattr(m, "tools", None) for m in middleware)

    def _register_mcp_tools(self, mcp_tools: list) -> None:
        if not mcp_tools:
            return
        for tool in mcp_tools:
            try:
                self._tool_registry.register(_make_mcp_tool_entry(tool))
            except Exception as exc:
                logger.warning("[LeonAgent] Failed to register MCP tool %s: %s", getattr(tool, "name", "<unknown>"), exc)

    def _create_placeholder_tool(self):
        """Create placeholder tool so the bound model still has a BaseTool."""
        from langchain_core.tools import tool

        @tool
        def _placeholder() -> str:
            """Internal placeholder for the empty-tool edge."""
            return ""

        return _placeholder

    def _get_agent_blocked_tools(self) -> set[str]:
        """Return disabled tool names, respecting catalog defaults.

        Logic:
        - Catalog default=True, absent from runtime.json → enabled
        - Catalog default=True, runtime enabled=False → blocked
        - Catalog default=False, absent from runtime.json → blocked (catalog wins)
        - Catalog default=False, runtime enabled=True → enabled (explicit override)
        """
        if not hasattr(self, "_agent_bundle") or not self._agent_bundle:
            return set()

        from config.defaults.tool_catalog import TOOLS_BY_NAME

        runtime = self._agent_bundle.runtime

        # Tools explicitly disabled in runtime.json
        blocked = {k.split(":", 1)[1] for k, v in runtime.items() if k.startswith("tools:") and not v.enabled}

        # Also block catalog tools with default=False that aren't explicitly enabled
        for tool_name, tool_def in TOOLS_BY_NAME.items():
            if tool_def.default:
                continue  # default=True: enabled unless explicitly blocked above
            runtime_key = f"tools:{tool_name}"
            if runtime_key not in runtime:
                blocked.add(tool_name)  # default=False and no explicit enable
            # If runtime_key exists with enabled=True, it's already excluded from blocked above

        return blocked

    def _get_mcp_server_configs(self) -> dict[str, Any]:
        if hasattr(self, "_agent_bundle") and self._agent_bundle and self._agent_bundle.mcp:
            return {name: srv for name, srv in self._agent_bundle.mcp.items() if not srv.disabled}
        return self.config.mcp.servers

    def _get_mcp_instruction_blocks(self) -> dict[str, str]:
        blocks: dict[str, str] = {}
        for name, cfg in self._get_mcp_server_configs().items():
            instructions = getattr(cfg, "instructions", None)
            if not isinstance(instructions, str) or not instructions.strip():
                continue
            blocks[name] = instructions.strip()
        return blocks

    def _load_config(
        self,
        agent_name: str | None,
        bundle_dir: str | Path | None,
        agent_config_id: str | None,
        agent_config_repo: Any,
        workspace_root: str | Path | None,
        sandbox_name: str | None,
        model_name: str | None,
        api_key: str | None,
        allowed_file_extensions: list[str] | None,
        block_dangerous_commands: bool | None,
        block_network_commands: bool | None,
        enable_audit_log: bool | None,
        enable_web_tools: bool | None,
        models_config_override: dict[str, Any] | None,
        memory_config_override: dict[str, Any] | None,
    ) -> tuple[LeonSettings, ModelsConfig]:
        """Load configuration using new config system.

        Returns:
            Tuple of (LeonSettings for runtime, ModelsConfig for model identity)
        """
        # Build CLI overrides for runtime config
        cli_overrides: dict = {}
        use_workspace_override = sandbox_name in (None, "", "local")

        if workspace_root is not None and use_workspace_override:
            # @@@remote-sandbox-config-root
            # Remote child agents may inherit a sandbox cwd like /home/daytona,
            # which is valid inside the sandbox but not on the host. Feeding that
            # path into LeonSettings makes config validation fail before sandbox
            # init ever runs, so only local sandboxes pin workspace_root here.
            cli_overrides["workspace_root"] = str(workspace_root)

        # Runtime overrides go into "runtime" section
        runtime_overrides: dict = {}
        if allowed_file_extensions is not None:
            runtime_overrides["allowed_extensions"] = allowed_file_extensions
        if block_dangerous_commands is not None:
            runtime_overrides["block_dangerous_commands"] = block_dangerous_commands
        if block_network_commands is not None:
            runtime_overrides["block_network_commands"] = block_network_commands
        if enable_audit_log is not None:
            runtime_overrides["enable_audit_log"] = enable_audit_log
        if runtime_overrides:
            cli_overrides["runtime"] = runtime_overrides

        if enable_web_tools is not None:
            cli_overrides.setdefault("tools", {}).setdefault("web", {})["enabled"] = enable_web_tools

        # Load runtime config
        loader = AgentLoader(workspace_root=workspace_root)
        config = loader.load(cli_overrides=cli_overrides or None)
        if memory_config_override is not None:
            config = self._with_memory_config_override(config, memory_config_override)

        # Load models config
        models_cli: dict = {}
        if model_name is not None:
            models_cli["active"] = {"model": model_name}
        models_loader = ModelsLoader(workspace_root=workspace_root)
        if models_config_override is None:
            models_config = models_loader.load(cli_overrides=models_cli or None)
        else:
            models_config = models_loader.load_with_user_config(
                models_config_override,
                cli_overrides=models_cli or None,
            )

        # @@@runtime-agent-config-root - web/runtime live agent startup must resolve from
        # the repo-rooted agent_config_id path, not stale local filesystem shells.
        if agent_config_id is not None:
            if agent_config_repo is None:
                raise RuntimeError("agent_config_repo is required when agent_config_id is provided")
            bundle = load_bundle_from_repo(agent_config_repo, agent_config_id)
            if bundle is None:
                raise RuntimeError(f"Agent config bundle not found: {agent_config_id}")
            self._agent_bundle = bundle
            self._agent_override = bundle.agent
        elif bundle_dir is not None:
            bundle_path = Path(bundle_dir).expanduser().resolve()
            self._agent_bundle = loader.load_bundle(bundle_path)
            self._agent_override = self._agent_bundle.agent.model_copy(update={"source_dir": bundle_path})
        # If agent specified, load agent definition to override system_prompt and tools
        elif agent_name:
            all_agents = loader.load_runtime_agents()
            agent_def = all_agents.get(agent_name)
            if not agent_def:
                available = ", ".join(sorted(all_agents.keys()))
                raise ValueError(f"Unknown agent: {agent_name}. Available: {available}")
            # If agent has source_dir, load the full bundle.
            if agent_def.source_dir:
                self._agent_bundle = loader.load_bundle(agent_def.source_dir)
            else:
                self._agent_bundle = None
            self._agent_override = agent_def
        else:
            self._agent_override = None
            self._agent_bundle = None

        if self.verbose:
            active_name = models_config.active.model if models_config.active else model_name
            print(f"[LeonAgent] Config: agent={agent_name or 'default'}, model={active_name}")

        return config, models_config

    @staticmethod
    def _with_memory_config_override(config: LeonSettings, memory_config_override: dict[str, Any]) -> LeonSettings:
        if not isinstance(memory_config_override, dict):
            raise TypeError("memory_config_override must be a JSON object")

        def merge_dict(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
            merged = dict(base)
            for key, value in patch.items():
                if isinstance(value, dict) and isinstance(merged.get(key), dict):
                    merged[key] = merge_dict(merged[key], value)
                else:
                    merged[key] = value
            return merged

        memory_data = merge_dict(config.memory.model_dump(), memory_config_override)
        return config.model_copy(update={"memory": type(config.memory)(**memory_data)})

    def _resolve_workspace_root(self) -> Path:
        """Resolve workspace root from config or current directory."""
        if self.config.workspace_root:
            return Path(self.config.workspace_root).expanduser().resolve()
        return Path.cwd()

    def _init_config_attributes(self) -> None:
        """Initialize configuration attributes from config."""
        self.allowed_file_extensions = self.config.runtime.allowed_extensions
        self.block_dangerous_commands = self.config.runtime.block_dangerous_commands
        self.block_network_commands = self.config.runtime.block_network_commands
        self.enable_audit_log = self.config.runtime.enable_audit_log
        self.enable_web_tools = self.config.tools.web.enabled

        self._session_pool: dict[str, Any] = {}
        env_db_path = os.getenv("LEON_DB_PATH")
        env_sandbox_db_path = os.getenv("LEON_SANDBOX_DB_PATH")
        self.db_path = Path(env_db_path).expanduser() if env_db_path else (Path.home() / ".leon" / "leon.db")
        self.sandbox_db_path = Path(env_sandbox_db_path).expanduser() if env_sandbox_db_path else (Path.home() / ".leon" / "sandbox.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.sandbox_db_path.parent.mkdir(parents=True, exist_ok=True)

    def _init_sandbox(self, sandbox: Any) -> Any:
        """Initialize sandbox infrastructure layer."""
        from sandbox import Sandbox as SandboxBase
        from sandbox import SandboxConfig, create_sandbox, resolve_sandbox_name

        if isinstance(sandbox, SandboxBase):
            return sandbox

        if isinstance(sandbox, str) or sandbox is None:
            sandbox_name = resolve_sandbox_name(sandbox)
            sandbox_config = SandboxConfig.load(sandbox_name)
            return create_sandbox(
                sandbox_config,
                workspace_root=str(self.workspace_root),
                db_path=self.sandbox_db_path,
            )

        raise TypeError(f"sandbox must be Sandbox, str, or None, got {type(sandbox)}")

    def _resolve_provider_name(self, model_name: str, overrides: dict | None = None) -> str | None:
        """Resolve provider: overrides → active config → infer from model name → configured default."""
        if overrides and overrides.get("model_provider"):
            return overrides["model_provider"]
        if self.models_config.active and self.models_config.active.provider:
            return self.models_config.active.provider
        from langchain.chat_models.base import _attempt_infer_model_provider

        inferred = _attempt_infer_model_provider(model_name)
        if inferred and self.models_config.get_provider(inferred):
            return inferred
        return self.models_config.get_model_provider()

    def _normalize_base_url(self, base_url: str, provider: str | None) -> str:
        """Normalize base_url based on provider requirements.

        Different providers have different URL conventions:
        - OpenAI/OpenRouter: expects base_url with /v1 (e.g., https://api.openai.com/v1)
        - Anthropic: expects base_url WITHOUT /v1 (SDK adds /v1/messages automatically)

        This method ensures user can provide base URL without /v1, and we add it when needed.

        Args:
            base_url: User-provided base URL (e.g., https://yunwu.ai)
            provider: Model provider (openai, anthropic, etc.)

        Returns:
            Normalized base URL
        """
        # Remove whitespace and trailing slash
        base_url = base_url.strip()
        base_url = base_url.rstrip("/")

        # Remove /v1 suffix if present (we'll add it back if needed)
        base_url = base_url.removesuffix("/v1")

        # Add /v1 for OpenAI-compatible providers
        if provider in ("openai", None):  # None defaults to OpenAI
            return f"{base_url}/v1"

        # Anthropic doesn't need /v1 (SDK adds /v1/messages automatically)
        if provider == "anthropic":
            return base_url

        # Default: add /v1
        return f"{base_url}/v1"

    def _create_model(self):
        """Initialize model with all parameters passed to init_chat_model.

        Uses configurable_fields so model/provider/api_key/base_url can be
        overridden per-request via LangGraph config without rebuilding the graph.
        """
        kwargs = normalize_model_kwargs(self.model_name, self._build_model_kwargs())
        return init_chat_model(
            self.model_name,
            api_key=self.api_key,
            configurable_fields=("model", "model_provider", "api_key", "base_url"),
            **kwargs,
        )

    def _create_extraction_model(self):
        """Create a small model for WebFetch AI extraction (leon:mini)."""
        model_name, overrides = self.models_config.resolve_model("leon:mini")
        provider = self._resolve_provider_name(model_name, overrides)
        kwargs: dict = {}
        if provider:
            kwargs["model_provider"] = provider

        api_key = self.models_config.resolve_api_key(provider) or getattr(self, "api_key", None)
        if not api_key:
            raise RuntimeError("API key required for WebFetch extraction model")
        kwargs["api_key"] = api_key

        base_url = self.models_config.resolve_base_url(provider)
        if base_url:
            kwargs["base_url"] = self._normalize_base_url(base_url, provider)
        return init_chat_model(model_name, **kwargs)

    def _build_model_kwargs(self) -> dict:
        """Build model parameters for model initialization and sub-agents."""
        kwargs = {}

        # Include virtual model overrides (filter out Leon-internal keys)
        if hasattr(self, "_model_overrides"):
            kwargs.update({k: v for k, v in self._model_overrides.items() if k not in ("context_limit", "based_on")})

        # Use provider from model overrides (mapping) first, then infer
        provider = self._resolve_provider_name(self.model_name, kwargs or None)
        if provider:
            kwargs["model_provider"] = provider

        base_url = self.models_config.resolve_base_url(provider)
        if base_url:
            kwargs["base_url"] = self._normalize_base_url(base_url, provider)

        if self.config.runtime.temperature is not None:
            kwargs["temperature"] = self.config.runtime.temperature
        if self.config.runtime.max_tokens is not None:
            kwargs["max_tokens"] = self.config.runtime.max_tokens

        kwargs.update(self.config.runtime.model_kwargs)

        # Enable usage reporting in streaming mode
        kwargs.setdefault("stream_usage", True)

        return kwargs

    def update_config(self, model: str | None = None, **tool_overrides) -> None:
        """Hot-reload model configuration (lightweight, no middleware/graph rebuild).

        Args:
            model: New model name (supports leon:* virtual names)
            **tool_overrides: Tool configuration overrides (runtime config only)
        """
        # Reload runtime config if tool overrides provided
        if tool_overrides:
            cli_overrides = {"tools": tool_overrides}
            loader = AgentLoader(workspace_root=self.workspace_root)
            self.config = loader.load(cli_overrides=cli_overrides)

        # Reload models config (picks up new API keys + model changes from disk)
        models_cli = {"active": {"model": model}} if model else None
        models_loader = ModelsLoader(workspace_root=self.workspace_root)
        self.models_config = models_loader.load(cli_overrides=models_cli)

        if model is None:
            # @@@api-key-reload — no model change, just refresh credentials from disk
            provider_name = self._resolve_provider_name(self.model_name, self._model_overrides)
            self.api_key = self.models_config.resolve_api_key(provider_name)
            base_url = self.models_config.resolve_base_url(provider_name)
            if base_url:
                base_url = self._normalize_base_url(base_url, provider_name)
            self._current_model_config.update(
                {
                    "api_key": self.api_key,
                    "base_url": base_url,
                }
            )
            return

        # Resolve virtual model
        active_model = self.models_config.active.model if self.models_config.active else model
        resolved_model, model_overrides = self.models_config.resolve_model(active_model)
        self.model_name = resolved_model
        self._model_overrides = model_overrides

        # Resolve provider credentials
        provider_name = self._resolve_provider_name(resolved_model, model_overrides)
        self.api_key = self.models_config.resolve_api_key(provider_name)
        base_url = self.models_config.resolve_base_url(provider_name)
        if base_url:
            base_url = self._normalize_base_url(base_url, provider_name)

        # Update stored config (no rebuild — configurable_fields handles the rest)
        self._current_model_config = {
            "model": resolved_model,
            "model_provider": provider_name,
            "api_key": self.api_key,
            "base_url": base_url,
        }

        # Update monitor (cost calculator + context_limit)
        if hasattr(self, "_monitor_middleware"):
            self._monitor_middleware.update_model(resolved_model, overrides=model_overrides)

        # Update memory middleware context_limit + model config
        if hasattr(self, "_memory_middleware"):
            from core.runtime.middleware.monitor.cost import get_model_context_limit

            lookup_name = model_overrides.get("based_on") or resolved_model
            self._memory_middleware.set_context_limit(model_overrides.get("context_limit") or get_model_context_limit(lookup_name))
            self._memory_middleware.set_model(self.model, self._current_model_config)

        if self.verbose:
            print(f"[LeonAgent] Config updated: model={resolved_model}")

    @property
    def observation_config(self) -> ObservationConfig:
        """Current observation provider configuration."""
        return self._observation_config

    def update_observation(self, **overrides) -> None:
        """Hot-reload observation configuration.

        Args:
            **overrides: Fields to override (e.g. active="langfuse" or active=None)
        """
        self._observation_config = ObservationLoader(workspace_root=self.workspace_root).load(
            cli_overrides=overrides or None
        )

        if self.verbose:
            print(f"[LeonAgent] Observation updated: active={self._observation_config.active}")

    def close(self, *, cleanup_sandbox: bool = True):
        """Clean up resources via CleanupRegistry (priority-ordered).

        Falls back to direct cleanup if CleanupRegistry is not initialized.
        """
        # @@@close-idempotent - child agents may explicitly skip sandbox cleanup
        # and later still hit __del__ on GC; never let a second close silently
        # re-enable default sandbox teardown on a shared lease.
        if getattr(self, "_closed", False) or getattr(self, "_closing", False):
            return

        self._closing = True
        session_end_error: Exception | None = None
        try:
            if getattr(self, "_session_started", False) and not getattr(self, "_session_ended", False):
                try:
                    self._run_async_cleanup(lambda: self._run_session_hooks("SessionEnd"), "SessionEnd hooks")
                except Exception as exc:
                    session_end_error = exc
                finally:
                    self._session_ended = True

            if hasattr(self, "_cleanup_registry") and cleanup_sandbox:
                self._run_async_cleanup(self._cleanup_registry.run_cleanup, "CleanupRegistry")
            else:
                # Fallback for edge cases where __init__ did not complete fully
                cleanup_steps = [
                    ("monitor", self._mark_terminated),
                    ("MCP client", self._cleanup_mcp_client),
                    ("SQLite connection", self._cleanup_sqlite_connection),
                ]
                if cleanup_sandbox:
                    cleanup_steps.insert(0, ("sandbox", self._cleanup_sandbox))

                for step_name, step_fn in cleanup_steps:
                    try:
                        step_fn()
                    except Exception as e:
                        print(f"[LeonAgent] {step_name} cleanup error: {e}")

            if session_end_error is not None:
                raise session_end_error
        finally:
            self._closed = True
            self._closing = False

    def _build_session_hook_payload(self, event: str) -> dict[str, Any]:
        return {
            "event": event,
            "session_id": self._bootstrap.session_id,
            "workspace_root": str(self.workspace_root),
            "cwd": str(self._bootstrap.cwd or self.workspace_root),
            "sandbox": self._sandbox.name,
        }

    async def _run_session_hooks(self, event: str) -> None:
        hooks = self._app_state.get_session_hooks(event)
        if not hooks:
            return

        payload = self._build_session_hook_payload(event)
        for hook in hooks:
            result = hook(payload)
            if inspect.isawaitable(result):
                await result

    def _cleanup_sandbox(self) -> None:
        """Clean up sandbox resources."""
        if hasattr(self, "_sandbox") and self._sandbox:
            try:
                self._sandbox.close()
            except Exception as e:
                print(f"[LeonAgent] Sandbox cleanup error: {e}")

    def _mark_terminated(self) -> None:
        """Mark agent as terminated."""
        if hasattr(self, "_monitor_middleware"):
            self._monitor_middleware.mark_terminated()

    _CLEANUP_TIMEOUT: float = 10.0  # seconds; prevents hanging on stuck I/O

    @staticmethod
    def _run_async_cleanup(coro_factory, label: str) -> None:
        import asyncio

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(coro_factory())
            return

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(asyncio.run, coro_factory())
            try:
                future.result(timeout=LeonAgent._CLEANUP_TIMEOUT)
            except concurrent.futures.TimeoutError:
                raise RuntimeError(
                    f"{label} cleanup timed out after {LeonAgent._CLEANUP_TIMEOUT}s — "
                    f"possible stuck I/O; resource abandoned to prevent hang"
                )
            except Exception as exc:
                raise RuntimeError(f"{label} cleanup failed: {exc}") from exc

    def _cleanup_mcp_client(self) -> None:
        """Clean up MCP client."""
        if not hasattr(self, "_mcp_client") or not self._mcp_client:
            return

        try:
            close_fn = getattr(self._mcp_client, "close", None)
            if callable(close_fn):
                self._run_async_cleanup(close_fn, "MCP client")
        except Exception as e:
            print(f"[LeonAgent] MCP cleanup error: {e}")
        self._mcp_client = None

    def _cleanup_sqlite_connection(self) -> None:
        """No-op: SQLite checkpointer removed; Postgres cleanup handled by _pg_saver_ctx."""

    def __del__(self):
        self.close()

    def _build_middleware_stack(self) -> list:
        """Build middleware stack.

        Order (outer → inner, i.e. index 0 = outermost):
          SpillBuffer → Monitor → PromptCaching → Memory → Steering → ToolRunner
        """
        middleware = []

        # Get backends from sandbox
        fs_backend = self._sandbox.fs()

        # 1. Monitor — second from outside; observes all model calls/responses.
        #    Must come before PromptCaching/Memory/Steering so token counts
        #    are captured before any request transformations.
        context_limit = self.config.runtime.context_limit
        self._monitor_middleware = MonitorMiddleware(
            context_limit=context_limit,
            model_name=self.model_name,
            verbose=self.verbose,
        )
        middleware.append(self._monitor_middleware)

        # 2. Prompt Caching — adds cache_control markers to model requests
        middleware.append(PromptCachingMiddleware(ttl="5m", min_messages_to_cache=0))

        # 3. Memory — prunes/compacts context before model call
        memory_enabled = self.config.memory.pruning.enabled or self.config.memory.compaction.enabled
        if memory_enabled:
            self._add_memory_middleware(middleware)

        # 4. MCP instructions delta — thread-scoped reminder when MCP guidance changes
        middleware.append(
            McpInstructionsDeltaMiddleware(
                get_instruction_blocks=self._get_mcp_instruction_blocks,
                get_app_state=lambda: self.app_state,
            )
        )

        # 5. Steering — injects queued messages before model call
        self._steering_middleware = SteeringMiddleware(queue_manager=self.queue_manager)
        middleware.append(self._steering_middleware)

        # 6. ToolRunner (innermost — routes all ToolRegistry-registered tool calls)
        self._tool_runner = ToolRunner(
            registry=self._tool_registry,
            validator=ToolValidator(),
        )
        middleware.append(self._tool_runner)

        # 0. SpillBuffer (outermost — catches oversized tool outputs)
        # Must be inserted at index 0 AFTER building the list:
        # QueryLoop composes middleware so the first entry remains outermost.
        if self.config.tools.spill_buffer.enabled:
            spill_cfg = self.config.tools.spill_buffer
            middleware.insert(
                0,
                SpillBufferMiddleware(
                    fs_backend=fs_backend,
                    workspace_root=self.workspace_root,
                    thresholds=spill_cfg.thresholds,
                    default_threshold=spill_cfg.default_threshold,
                ),
            )

        return middleware

    def _add_memory_middleware(self, middleware: list) -> None:
        """Add memory middleware to stack."""
        # @@@context-limit-default - prefer mapping override (e.g. leon:tiny -> 8000),
        # then Monitor's resolved value (model API or its 128000 default).
        context_limit = self._model_overrides.get("context_limit") or self._monitor_middleware._context_monitor.context_limit
        pruning_config = self.config.memory.pruning
        compaction_config = self.config.memory.compaction

        db_path = self.db_path
        # @@@memory-storage-consumer - memory summary persistence must consume injected storage container, not fixed sqlite path.
        summary_repo = self.storage_container.summary_repo() if self.storage_container is not None else None
        self._memory_middleware = MemoryMiddleware(
            context_limit=context_limit,
            pruning_config=pruning_config,
            compaction_config=compaction_config,
            db_path=db_path,
            summary_repo=summary_repo,
            checkpointer=self.checkpointer,
            compaction_threshold=0.7,
            verbose=self.verbose,
        )
        # Cap keep_recent_tokens for small context windows
        self._memory_middleware.set_context_limit(context_limit)
        middleware.append(self._memory_middleware)

    def _init_services(self) -> None:
        """Initialize tool Services and register them with ToolRegistry.

        Each Service registers its tools (INLINE or DEFERRED) into self._tool_registry.
        This runs after sandbox init so backends are available.
        """
        fs_backend = self._sandbox.fs()
        cmd_executor = self._sandbox.shell()

        # FileSystem tools
        if self.config.tools.filesystem.enabled:
            file_hooks = []
            if self._sandbox.name == "local":
                if self.enable_audit_log:
                    file_hooks.append(
                        FileAccessLoggerHook(
                            workspace_root=self.workspace_root,
                            log_file="file_access.log",
                        )
                    )
                file_hooks.append(
                    FilePermissionHook(
                        workspace_root=self.workspace_root,
                        allowed_extensions=self.allowed_file_extensions,
                    )
                )
            max_file_size = self.config.tools.filesystem.max_file_size
            self._filesystem_service = FileSystemService(
                registry=self._tool_registry,
                workspace_root=self.workspace_root,
                max_file_size=max_file_size,
                allowed_extensions=self.allowed_file_extensions,
                hooks=file_hooks,
                operation_recorder=get_recorder(),
                backend=fs_backend,
                extra_allowed_paths=self.extra_allowed_paths,
            )

        # Search tools
        if self.config.tools.search.enabled:
            max_file_size = self.config.tools.search.tools.grep.max_file_size
            self._search_service = SearchService(
                registry=self._tool_registry,
                workspace_root=self.workspace_root,
                max_file_size=max_file_size,
            )

        # Web tools
        if self.config.tools.web.enabled:
            tavily_key = self.config.tools.web.tools.web_search.tavily_api_key or os.getenv("TAVILY_API_KEY")
            exa_key = self.config.tools.web.tools.web_search.exa_api_key or os.getenv("EXA_API_KEY")
            firecrawl_key = self.config.tools.web.tools.web_search.firecrawl_api_key or os.getenv("FIRECRAWL_API_KEY")
            jina_key = self.config.tools.web.tools.web_fetch.jina_api_key or os.getenv("JINA_AI_API_KEY")
            extraction_model = self._create_extraction_model()
            self._web_service = WebService(
                registry=self._tool_registry,
                tavily_api_key=tavily_key,
                exa_api_key=exa_key,
                firecrawl_api_key=firecrawl_key,
                jina_api_key=jina_key,
                max_search_results=self.config.tools.web.tools.web_search.max_results,
                timeout=self.config.tools.web.timeout,
                extraction_model=extraction_model,
            )

        # Shared background run registry: CommandService (bash) and AgentService (agent)
        # both write here; TaskOutput/TaskStop read from here.
        self._background_runs: dict = {}

        # Command tools
        if self.config.tools.command.enabled:
            command_hooks = []
            if self._sandbox.name == "local":
                if self.block_dangerous_commands:
                    command_hooks.append(
                        DangerousCommandsHook(
                            workspace_root=self.workspace_root,
                            block_network=self.block_network_commands,
                            verbose=self.verbose,
                        )
                    )
            self._command_service = CommandService(
                registry=self._tool_registry,
                workspace_root=self.workspace_root,
                hooks=command_hooks,
                executor=cmd_executor,
                queue_manager=self.queue_manager,
                background_runs=self._background_runs,
            )

        # Skills tools
        if self.config.skills.enabled and self.config.skills.paths:
            # Use the agent bundle's skills enabled/disabled state if available.
            enabled_skills = self.config.skills.skills
            if hasattr(self, "_agent_bundle") and self._agent_bundle:
                bundle_skill_entries = {k.split(":", 1)[1]: v for k, v in self._agent_bundle.runtime.items() if k.startswith("skills:")}
                if bundle_skill_entries:
                    enabled_skills = {name: rc.enabled for name, rc in bundle_skill_entries.items()}
            self._skills_service = SkillsService(
                registry=self._tool_registry,
                skill_paths=self.config.skills.paths,
                enabled_skills=enabled_skills,
            )

        # Task tools (DEFERRED - discoverable via tool_search)
        self._task_service = TaskService(
            registry=self._tool_registry,
        )

        self._mcp_resource_tool_service = McpResourceToolService(
            registry=self._tool_registry,
            client_fn=lambda: getattr(self, "_mcp_client", None),
            server_configs_fn=self._get_mcp_server_configs,
        )

        # ToolSearch (INLINE - always available for discovering DEFERRED tools)
        self._tool_search_service = ToolSearchService(
            registry=self._tool_registry,
        )

        # Multi-agent tools (Agent/TaskOutput/TaskStop)
        self._agent_registry = AgentRegistry()
        self._agent_service = AgentService(
            tool_registry=self._tool_registry,
            agent_registry=self._agent_registry,
            workspace_root=self.workspace_root,
            model_name=self.model_name,
            thread_repo=self._thread_repo,
            user_repo=self._user_repo,
            queue_manager=self.queue_manager,
            shared_runs=self._background_runs,
            web_app=self._web_app,
            child_agent_factory=create_leon_agent,
        )

        # Team coordination (TeamCreate/TeamDelete — deferred mode)
        # @@@teams-removed - TeamService module doesn't exist, feature not implemented
        # self._team_service = TeamService(
        #     tool_registry=self._tool_registry,
        # )

        # @@@chat-tools - register chat tools for agents with user identity (v2 messaging)
        if self._chat_repos:
            repos = self._chat_repos
            chat_identity_id = self._runtime_chat_identity_id()
            if chat_identity_id:
                from messaging.tools.chat_tool_service import ChatToolService

                self._chat_tool_service = ChatToolService(
                    registry=self._tool_registry,
                    chat_identity_id=chat_identity_id,
                    messaging_service=repos.get("messaging_service"),
                )

        # LSP tools — DEFERRED, always registered, multilspy checked at call time
        self._lsp_service = None
        try:
            from core.tools.lsp.service import LSPService

            self._lsp_service = LSPService(
                registry=self._tool_registry,
                workspace_root=self.workspace_root,
            )
        except Exception as e:
            logger.debug("[LeonAgent] LSPService init skipped: %s", e)

        if self.verbose:
            all_tools = self._tool_registry.list_all()
            inline = [t for t in all_tools if t.mode.value == "inline"]
            deferred = [t for t in all_tools if t.mode.value == "deferred"]
            print(f"[LeonAgent] ToolRegistry: {len(inline)} inline, {len(deferred)} deferred tools")

    async def _init_mcp_tools(self) -> list:
        mcp_enabled = self.config.mcp.enabled

        mcp_servers = self._get_mcp_server_configs()

        if not mcp_enabled or not mcp_servers:
            return []

        from langchain_mcp_adapters.client import MultiServerMCPClient

        configs = {}
        for name, cfg in mcp_servers.items():
            transport = getattr(cfg, "transport", None)
            if cfg.url:
                # @@@mcp-transport-honesty - api-04 requires explicit transport
                # config to survive loader -> runtime. URL-based MCP is not
                # always streamable_http; websocket/sse must stay explicit.
                config = {
                    "transport": transport or "streamable_http",
                    "url": cfg.url,
                }
            else:
                config = {
                    "transport": transport or "stdio",
                    "command": cfg.command,
                    "args": cfg.args,
                }
            if cfg.env:
                config["env"] = cfg.env
            configs[name] = config

        try:
            client = MultiServerMCPClient(configs, tool_name_prefix=False)
            self._mcp_client = client  # Save reference for cleanup
            tools = await client.get_tools()

            # Apply mcp__ prefix to match Claude Code naming convention
            for tool in tools:
                # Extract server name from tool metadata or connection
                server_name = None
                for name in configs:
                    if hasattr(tool, "metadata") and tool.metadata:
                        server_name = name
                        break
                if server_name:
                    tool.name = f"mcp__{server_name}__{tool.name}"

            if any(cfg.allowed_tools for cfg in mcp_servers.values()):
                tools = [t for t in tools if self._is_tool_allowed(t)]

            if self.verbose:
                print(f"[LeonAgent] Loaded {len(tools)} MCP tools from {len(configs)} servers")
            return tools
        except Exception as e:
            if self.verbose:
                print(f"[LeonAgent] MCP initialization failed: {e}")
            return []

    async def _init_checkpointer(self):
        """Initialize async checkpointer for conversation persistence.

        Requires LEON_POSTGRES_URL to be set (Supabase Postgres).
        """
        pg_url = os.getenv("LEON_POSTGRES_URL")
        if not pg_url:
            raise RuntimeError("LEON_POSTGRES_URL is required for checkpointer initialization")

        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        # from_conn_string is an async context manager; enter it and keep
        # the reference so the connection pool stays open for the agent's lifetime.
        self._pg_saver_ctx = AsyncPostgresSaver.from_conn_string(pg_url)
        self.checkpointer = await self._pg_saver_ctx.__aenter__()
        await self.checkpointer.setup()

    def _is_tool_allowed(self, tool) -> bool:
        # Extract original tool name without mcp__ prefix
        tool_name = tool.name
        if tool_name.startswith("mcp__"):
            parts = tool_name.split("__", 2)
            if len(parts) == 3:
                tool_name = parts[2]

        mcp_servers = self.config.mcp.servers

        for cfg in mcp_servers.values():
            if cfg.allowed_tools:
                return tool_name in cfg.allowed_tools
        return True

    def _build_system_prompt(self) -> str:
        """Build system prompt based on sandbox mode."""
        # If agent override is set, use its system_prompt + rules.
        if hasattr(self, "_agent_override") and self._agent_override:
            prompt = self._agent_override.system_prompt
            # Append bundle rules (from rules/*.md) to system prompt
            if hasattr(self, "_agent_bundle") and self._agent_bundle and self._agent_bundle.rules:
                rule_parts = [f"## {r['name']}\n{r['content']}" for r in self._agent_bundle.rules if r.get("content", "").strip()]
                if rule_parts:
                    prompt += "\n\n---\n\n" + "\n\n".join(rule_parts)
            return prompt

        prompt = self._build_base_prompt()
        prompt += self._build_common_prompt_sections()

        if self.allowed_file_extensions:
            prompt += f"\n6. **File Type Restriction**: Only these extensions allowed: {', '.join(self.allowed_file_extensions)}\n"

        return prompt

    def _runtime_chat_identity_id(self) -> str | None:
        if not self._chat_repos:
            return None
        chat_identity_id = self._chat_repos.get("chat_identity_id")
        if chat_identity_id:
            return str(chat_identity_id)
        if self._chat_repos.get("user_id"):
            raise RuntimeError("chat_repos.user_id is no longer supported; use chat_identity_id")
        return None

    def _compose_system_prompt(self) -> str:
        prompt = self._build_system_prompt()

        custom_prompt = self.config.system_prompt
        if custom_prompt:
            prompt += f"\n\n**Custom Instructions:**\n{custom_prompt}"

        # @@@chat-identity — inject chat identity so agent knows who it is in the social layer
        if self._chat_repos:
            repos = self._chat_repos
            uid = self._runtime_chat_identity_id()
            owner_uid = repos.get("owner_id", "")
            if uid:
                user_repo = repos.get("user_repo")
                self_user = user_repo.get_by_id(uid) if user_repo else None
                owner_row = user_repo.get_by_id(owner_uid) if user_repo and owner_uid else None
                name = self_user.display_name if self_user else uid
                owner_name = owner_row.display_name if owner_row else "unknown"
                prompt += (
                    f"\n\n**Chat Identity:**\n"
                    f"- Your name: {name}\n"
                    f"- Your chat identity id: {uid}\n"
                    f"- Your owner: {owner_name} (human user_id: {owner_uid})\n"
                    f"- For 1:1 chat tools, use participant_id for the other user's social id.\n"
                    f"- When you receive a chat notification, you MUST read it with read_messages() before deciding what to do.\n"
                    f"- If that notification already gives you a chat_id, prefer using that exact chat_id directly.\n"
                    f"- If you reply to the other party, you MUST call send_message(). Never claim you replied unless send_message() succeeded.\n"
                    f"- Your normal text output goes to your owner's thread, not to the chat — only send_message() delivers to the other party.\n"
                )
        return prompt

    def _invalidate_system_prompt_cache(self) -> None:
        self._system_prompt_section_cache.clear()

    def _get_cached_prompt_section(self, key: str, builder) -> str:
        cached = self._system_prompt_section_cache.get(key)
        if cached is not None:
            return cached
        value = builder()
        self._system_prompt_section_cache[key] = value
        return value

    def _build_context_section(self) -> str:
        from core.runtime.prompts import build_context_section

        def _build() -> str:
            is_sandbox = self._sandbox.name != "local"
            if is_sandbox:
                return build_context_section(
                    sandbox_name=self._sandbox.name,
                    sandbox_env_label=self._sandbox.env_label,
                    sandbox_working_dir=self._sandbox.working_dir,
                )
            import platform

            os_name = platform.system()
            shell_name = "powershell" if os_name == "Windows" else os.environ.get("SHELL", "/bin/bash").split("/")[-1]
            return build_context_section(
                sandbox_name="local",
                workspace_root=str(self.workspace_root),
                os_name=os_name,
                shell_name=shell_name,
            )

        return self._get_cached_prompt_section("context", _build)

    def _build_rules_section(self) -> str:
        from core.runtime.prompts import build_rules_section

        def _build() -> str:
            is_sandbox = self._sandbox.name != "local"
            working_dir = self._sandbox.working_dir if is_sandbox else str(self.workspace_root)
            return build_rules_section(
                is_sandbox=is_sandbox,
                sandbox_name=self._sandbox.name,
                working_dir=working_dir,
                workspace_root=str(self.workspace_root),
                spill_buffer_enabled=self.config.tools.spill_buffer.enabled,
                spill_keep_recent=self.config.memory.pruning.protect_recent,
            )

        return self._get_cached_prompt_section("rules", _build)

    def _build_base_prompt(self) -> str:
        from core.runtime.prompts import build_base_prompt

        return self._get_cached_prompt_section(
            "base_prompt",
            lambda: build_base_prompt(self._build_context_section(), self._build_rules_section()),
        )

    def _build_common_prompt_sections(self) -> str:
        from core.runtime.prompts import build_common_sections

        return self._get_cached_prompt_section(
            "common_sections",
            lambda: build_common_sections(bool(self.config.skills.enabled and self.config.skills.paths)),
        )

    def invoke(self, message: str, thread_id: str = "default") -> dict:
        """Invoke agent with a message (sync version).

        Args:
            message: User message
            thread_id: Thread ID

        Returns:
            Agent response (includes messages and state)
        """
        import asyncio

        async def _ainvoke():
            return await self.agent.ainvoke(
                {"messages": [{"role": "user", "content": message}]},
                config={"configurable": {"thread_id": thread_id}},
            )

        try:
            # Reuse the event loop created during initialization
            if hasattr(self, "_event_loop") and self._event_loop:
                return self._event_loop.run_until_complete(_ainvoke())
            # Fallback to asyncio.run() if no loop exists
            return asyncio.run(_ainvoke())
        except Exception as e:
            self._monitor_middleware.mark_error(e)
            raise

    async def ainvoke(self, message: str, thread_id: str = "default") -> dict:
        """Invoke agent with a message (async version).

        Args:
            message: User message
            thread_id: Thread ID

        Returns:
            Agent response (includes messages and state)
        """
        try:
            return await self.agent.ainvoke(
                {"messages": [{"role": "user", "content": message}]},
                config={"configurable": {"thread_id": thread_id}},
            )
        except Exception as e:
            self._monitor_middleware.mark_error(e)
            raise

    async def astream(
        self,
        message: str,
        thread_id: str = "default",
        stream_mode: str | list[str] = "updates",
        max_budget_usd: float | None = None,
    ):
        """Stream agent output through a caller-owned LeonAgent surface."""
        try:
            async for chunk in self.agent.astream(
                {"messages": [{"role": "user", "content": message}]},
                config={"configurable": {"thread_id": thread_id}},
                stream_mode=stream_mode,
            ):
                yield chunk
                if max_budget_usd is not None and self.runtime.cost > max_budget_usd:
                    raise RuntimeError(f"max_budget_usd exceeded: cost={self.runtime.cost:.6f} budget={max_budget_usd:.6f}")
        except Exception as e:
            self._monitor_middleware.mark_error(e)
            raise

    async def aclear_thread(self, thread_id: str = "default") -> None:
        """Clear turn-scoped state for a thread while preserving session accumulators."""
        try:
            await self.agent.aclear(thread_id)
            self._invalidate_system_prompt_cache()
            self.system_prompt = self._compose_system_prompt()
            self.agent.system_prompt = SystemMessage(content=[{"type": "text", "text": self.system_prompt}])
        except Exception as e:
            self._monitor_middleware.mark_error(e)
            raise

    def clear_thread(self, thread_id: str = "default") -> None:
        """Sync wrapper for aclear_thread()."""
        import asyncio

        async def _aclear():
            await self.aclear_thread(thread_id)

        try:
            if hasattr(self, "_event_loop") and self._event_loop:
                self._event_loop.run_until_complete(_aclear())
            else:
                asyncio.run(_aclear())
        except Exception as e:
            self._monitor_middleware.mark_error(e)
            raise

    def get_pending_permission_requests(self, thread_id: str | None = None) -> list[dict]:
        requests = list(self._app_state.pending_permission_requests.values())
        if thread_id is not None:
            requests = [item for item in requests if item.get("thread_id") == thread_id]
        return requests

    def get_thread_permission_rules(self, thread_id: str | None = None) -> dict[str, Any]:
        state = self._app_state.tool_permission_context
        return {
            "thread_id": thread_id,
            "scope": "session",
            "managed_only": state.allowManagedPermissionRulesOnly,
            "rules": {
                "allow": list(state.alwaysAllowRules.get("session", [])),
                "deny": list(state.alwaysDenyRules.get("session", [])),
                "ask": list(state.alwaysAskRules.get("session", [])),
            },
        }

    def add_thread_permission_rule(self, thread_id: str, *, behavior: str, tool_name: str) -> bool:
        if self._app_state.tool_permission_context.allowManagedPermissionRulesOnly:
            return False

        def _update(state: AppState) -> AppState:
            permission_state = state.tool_permission_context.model_copy(deep=True)
            for bucket in (
                permission_state.alwaysAllowRules.setdefault("session", []),
                permission_state.alwaysDenyRules.setdefault("session", []),
                permission_state.alwaysAskRules.setdefault("session", []),
            ):
                while tool_name in bucket:
                    bucket.remove(tool_name)
            target_bucket = {
                "allow": permission_state.alwaysAllowRules.setdefault("session", []),
                "deny": permission_state.alwaysDenyRules.setdefault("session", []),
                "ask": permission_state.alwaysAskRules.setdefault("session", []),
            }[behavior]
            if tool_name not in target_bucket:
                target_bucket.append(tool_name)
            return state.model_copy(update={"tool_permission_context": permission_state})

        self._app_state.set_state(_update)
        return True

    def remove_thread_permission_rule(self, thread_id: str, *, behavior: str, tool_name: str) -> bool:
        removed = False

        def _update(state: AppState) -> AppState:
            nonlocal removed
            permission_state = state.tool_permission_context.model_copy(deep=True)
            bucket = {
                "allow": permission_state.alwaysAllowRules.setdefault("session", []),
                "deny": permission_state.alwaysDenyRules.setdefault("session", []),
                "ask": permission_state.alwaysAskRules.setdefault("session", []),
            }[behavior]
            if tool_name in bucket:
                bucket.remove(tool_name)
                removed = True
            return state.model_copy(update={"tool_permission_context": permission_state})

        self._app_state.set_state(_update)
        return removed

    def resolve_permission_request(
        self,
        request_id: str,
        *,
        decision: str,
        message: str | None = None,
        answers: list[dict[str, Any]] | None = None,
        annotations: dict[str, Any] | None = None,
    ) -> bool:
        pending = self._app_state.pending_permission_requests.get(request_id)
        if pending is None:
            return False

        resolved = dict(self._app_state.resolved_permission_requests)
        payload = {
            **pending,
            "decision": decision,
            "message": message or pending.get("message"),
        }
        if answers is not None:
            payload["answers"] = answers
        if annotations is not None:
            payload["annotations"] = annotations
        resolved[request_id] = payload
        still_pending = dict(self._app_state.pending_permission_requests)
        still_pending.pop(request_id, None)
        self._app_state.set_state(
            lambda prev: prev.model_copy(
                update={
                    "pending_permission_requests": still_pending,
                    "resolved_permission_requests": resolved,
                }
            )
        )
        return True

    def drop_permission_request(self, request_id: str) -> bool:
        had_pending = request_id in self._app_state.pending_permission_requests
        had_resolved = request_id in self._app_state.resolved_permission_requests
        if not had_pending and not had_resolved:
            return False

        def _drop(state: AppState) -> AppState:
            pending = dict(state.pending_permission_requests)
            resolved = dict(state.resolved_permission_requests)
            pending.pop(request_id, None)
            resolved.pop(request_id, None)
            return state.model_copy(
                update={
                    "pending_permission_requests": pending,
                    "resolved_permission_requests": resolved,
                }
            )

        self._app_state.set_state(_drop)
        return True

    def get_response(self, message: str, thread_id: str = "default", **kwargs) -> str:
        """Get agent's text response.

        Args:
            message: User message
            thread_id: Thread ID
            **kwargs: Additional state parameters

        Returns:
            Agent's text response
        """
        result = self.invoke(message, thread_id, **kwargs)
        return result["messages"][-1].content

    def cleanup(self):
        """Clean up temporary workspace directory."""
        if self.workspace_root.exists() and "tmp" in str(self.workspace_root):
            import shutil

            shutil.rmtree(self.workspace_root, ignore_errors=True)


def create_leon_agent(
    model_name: str | None = None,
    api_key: str | None = None,
    workspace_root: str | Path | None = None,
    sandbox: Any = None,
    storage_container: StorageContainer | None = None,
    **kwargs,
) -> LeonAgent:
    """Create Leon Agent.

    Args:
        model_name: Model name. None means "let LeonAgent resolve defaults".
        api_key: API key
        workspace_root: Workspace directory
        sandbox: Sandbox instance, name string, or None for local
        storage_container: Optional pre-built storage container (runtime wiring injection)
        **kwargs: Additional configuration parameters

    Returns:
        Configured LeonAgent instance

    Examples:
        # Basic usage
        agent = create_leon_agent()

        # With sandbox
        agent = create_leon_agent(sandbox="agentbay")

        # Custom workspace
        agent = create_leon_agent(workspace_root="/path/to/workspace")
    """
    # Filter out kwargs that LeonAgent.__init__ doesn't accept (e.g. profile from CLI)
    import inspect as _inspect

    from storage.runtime import build_storage_container, uses_supabase_storage

    if storage_container is None and uses_supabase_storage():
        storage_container = build_storage_container()

    _valid = set(_inspect.signature(LeonAgent.__init__).parameters) - {"self"}
    kwargs = {k: v for k, v in kwargs.items() if k in _valid}
    return LeonAgent(
        model_name=model_name,
        api_key=api_key,
        workspace_root=workspace_root,
        sandbox=sandbox,
        storage_container=storage_container,
        **kwargs,
    )


if __name__ == "__main__":
    # Example usage
    leon_agent = create_leon_agent()

    try:
        print("=== Example 1: File Operations ===")
        response = leon_agent.get_response(
            f"Create a Python file at {leon_agent.workspace_root}/hello.py that prints 'Hello, Leon!'",
            thread_id="demo",
        )
        print(response)
        print()

        print("=== Example 2: Read File ===")
        response = leon_agent.get_response(f"Read the file {leon_agent.workspace_root}/hello.py", thread_id="demo")
        print(response)
        print()

        print("=== Example 3: Search ===")
        response = leon_agent.get_response(f"Search for 'Hello' in {leon_agent.workspace_root}", thread_id="demo")
        print(response)

    finally:
        leon_agent.cleanup()
