#!/usr/bin/env python3
"""
Leon CLI - Textual TUI 模式

使用 Textual 框架构建的现代化终端界面
"""

import argparse
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path

from config.schema import DEFAULT_MODEL
from tui.config import ConfigManager, interactive_config, show_config
from tui.session import SessionManager


def format_relative_time(dt: datetime | str | None) -> str:
    """Format datetime as relative time string"""
    if dt is None:
        return "未知"
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt)
        except Exception:
            return dt

    now = datetime.now()
    diff = now - dt
    seconds = diff.total_seconds()

    if seconds < 60:
        return "刚刚"
    elif seconds < 3600:
        minutes = int(seconds / 60)
        return f"{minutes} 分钟前"
    elif seconds < 86400:
        hours = int(seconds / 3600)
        return f"{hours} 小时前"
    else:
        days = int(seconds / 86400)
        return f"{days} 天前"


def cmd_thread_list(args):
    """List all conversation threads"""
    from rich.console import Console
    from rich.table import Table

    console = Console()
    session_mgr = SessionManager()

    # Get threads from session
    threads = session_mgr.get_threads()

    if not threads:
        console.print("[yellow]暂无对话记录[/yellow]")
        return

    # Try to get more info from database
    db_threads = session_mgr.get_threads_from_db()
    db_info = {t["thread_id"]: t for t in db_threads}

    # Get message counts using TimeTravelManager
    from tui.time_travel import TimeTravelManager

    time_travel_mgr = TimeTravelManager()

    table = Table(title="对话列表")
    table.add_column("Thread ID", style="cyan")
    table.add_column("消息", style="magenta", justify="right")
    table.add_column("首条消息", style="white", max_width=30)
    table.add_column("最后活跃", style="green")
    table.add_column("状态", style="yellow")

    last_thread = session_mgr.get_last_thread_id()

    for thread_id in threads:
        info = db_info.get(thread_id, {})
        last_active = format_relative_time(info.get("last_active"))
        status = "(当前)" if thread_id == last_thread else ""

        # Get message count and first message
        checkpoints = time_travel_mgr.get_checkpoints(thread_id, user_turns_only=True)
        msg_count = str(len(checkpoints)) if checkpoints else "0"
        first_msg = "-"
        if checkpoints and checkpoints[0].user_message:
            first_msg = checkpoints[0].user_message
            if len(first_msg) > 28:
                first_msg = first_msg[:28] + "…"

        table.add_row(thread_id, msg_count, first_msg, last_active, status)

    console.print(table)


def cmd_thread_history(args):
    """Show checkpoint history for a thread"""
    from rich.console import Console
    from rich.table import Table

    console = Console()
    thread_id = args.thread_id

    db_path = Path.home() / ".leon" / "leon.db"
    if not db_path.exists():
        console.print("[red]数据库不存在[/red]")
        return

    from tui.time_travel import TimeTravelManager

    time_travel_mgr = TimeTravelManager()
    checkpoints = time_travel_mgr.get_checkpoints(thread_id, user_turns_only=True)

    if not checkpoints:
        console.print(f"[yellow]对话 {thread_id} 暂无历史节点[/yellow]")
        return

    table = Table(title=f"对话历史: {thread_id}")
    table.add_column("#", style="dim")
    table.add_column("Checkpoint ID", style="cyan")
    table.add_column("时间", style="green")
    table.add_column("消息", style="white")
    table.add_column("文件操作", style="yellow")

    for i, cp in enumerate(checkpoints):
        time_str = format_relative_time(cp.timestamp)
        msg = cp.user_message or "-"
        if len(msg) > 40:
            msg = msg[:40] + "..."
        ops = str(cp.file_operations_count) if cp.file_operations_count > 0 else "-"
        current = " (当前)" if cp.is_current else ""
        table.add_row(
            str(i + 1) + current,
            cp.checkpoint_id[:12] + "...",
            time_str,
            msg,
            ops,
        )

    console.print(table)


def cmd_thread_rewind(args):
    """Rewind a thread to a specific checkpoint"""
    from rich.console import Console

    console = Console()
    thread_id = args.thread_id
    checkpoint_id = args.checkpoint_id

    db_path = Path.home() / ".leon" / "leon.db"
    if not db_path.exists():
        console.print("[red]数据库不存在[/red]")
        return

    from tui.time_travel import TimeTravelManager

    time_travel_mgr = TimeTravelManager()

    # Find the checkpoint
    checkpoints = time_travel_mgr.get_checkpoints(thread_id)
    target_cp = None

    for cp in checkpoints:
        if cp.checkpoint_id.startswith(checkpoint_id):
            target_cp = cp
            break

    if not target_cp:
        console.print(f"[red]找不到 checkpoint: {checkpoint_id}[/red]")
        return

    # Show what will be reverted
    ops_to_revert = time_travel_mgr.get_operations_to_revert(thread_id, target_cp.checkpoint_id)

    if ops_to_revert:
        console.print(f"[yellow]将撤销 {len(ops_to_revert)} 个文件操作:[/yellow]")
        for op in ops_to_revert[:5]:
            console.print(f"  - {op.operation_type}: {op.file_path}")
        if len(ops_to_revert) > 5:
            console.print(f"  ... 还有 {len(ops_to_revert) - 5} 个操作")

    # Confirm
    if not args.yes:
        confirm = input("\n确认回退? [y/N] ")
        if confirm.lower() != "y":
            console.print("[yellow]已取消[/yellow]")
            return

    # Execute rewind
    result = time_travel_mgr.rewind_to(thread_id, target_cp.checkpoint_id)

    if result.success:
        console.print(f"[green]✓ {result.message}[/green]")
    else:
        console.print(f"[red]✗ {result.message}[/red]")
        for error in result.errors:
            console.print(f"  [red]{error}[/red]")


def cmd_thread_rm(args):
    """Delete a thread"""
    from rich.console import Console

    console = Console()
    thread_id = args.thread_id

    session_mgr = SessionManager()

    # Confirm
    if not args.yes:
        confirm = input(f"确认删除对话 {thread_id}? [y/N] ")
        if confirm.lower() != "y":
            console.print("[yellow]已取消[/yellow]")
            return

    if session_mgr.delete_thread(thread_id):
        console.print(f"[green]✓ 已删除对话: {thread_id}[/green]")
    else:
        console.print("[red]✗ 删除失败[/red]")


def _init_sandbox_providers() -> tuple[dict, dict]:
    """Load sandbox providers and managers from ~/.leon/sandboxes/*.json.

    Returns (providers, managers) dicts keyed by provider name.
    """
    from sandbox.config import SandboxConfig
    from sandbox.manager import SandboxManager

    providers: dict[str, object] = {}
    sandboxes_dir = Path.home() / ".leon" / "sandboxes"
    if not sandboxes_dir.exists():
        return {}, {}

    for config_file in sandboxes_dir.glob("*.json"):
        name = config_file.stem
        try:
            config = SandboxConfig.load(name)
            provider = _create_provider(config)
            if provider:
                providers[config.provider] = provider
        except Exception as e:
            print(f"[sandbox] Failed to load {name}: {e}")

    managers = {name: SandboxManager(provider=provider) for name, provider in providers.items()}
    return providers, managers


def _create_provider(config):
    """Create provider instance from config"""
    import os

    if config.provider == "agentbay":
        from sandbox.providers.agentbay import AgentBayProvider

        key = config.agentbay.api_key or os.getenv("AGENTBAY_API_KEY")
        if key:
            return AgentBayProvider(
                api_key=key,
                region_id=config.agentbay.region_id,
                default_context_path=config.agentbay.context_path,
                image_id=config.agentbay.image_id,
            )

    elif config.provider == "docker":
        from sandbox.providers.docker import DockerProvider

        return DockerProvider(
            image=config.docker.image,
            mount_path=config.docker.mount_path,
            default_cwd=config.docker.cwd,
        )

    elif config.provider == "e2b":
        from sandbox.providers.e2b import E2BProvider

        key = config.e2b.api_key or os.getenv("E2B_API_KEY")
        if key:
            return E2BProvider(
                api_key=key,
                template=config.e2b.template,
                default_cwd=config.e2b.cwd,
                timeout=config.e2b.timeout,
            )

    elif config.provider == "daytona":
        from sandbox.providers.daytona import DaytonaProvider

        key = config.daytona.api_key or os.getenv("DAYTONA_API_KEY")
        if key:
            return DaytonaProvider(
                api_key=key,
                api_url=config.daytona.api_url,
                target=config.daytona.target,
                default_cwd=config.daytona.cwd,
            )

    return None


def _load_all_sessions(managers: dict) -> list[dict]:
    """Load sessions from all managers in parallel."""
    from concurrent.futures import ThreadPoolExecutor

    def _fetch(manager):
        return manager.list_sessions()

    sessions = []
    with ThreadPoolExecutor(max_workers=len(managers) or 1) as pool:
        for rows in pool.map(_fetch, managers.values()):
            for row in rows:
                sessions.append(
                    {
                        "id": row["session_id"],
                        "status": row["status"],
                        "provider": row["provider"],
                        "thread": row["thread_id"],
                    }
                )
    return sessions


def _find_session(sessions: list[dict], session_id_prefix: str) -> dict | None:
    """Find session by ID or prefix."""
    for s in sessions:
        if s["id"] == session_id_prefix or s["id"].startswith(session_id_prefix):
            return s
    return None


def cmd_sandbox(args):
    """Handle sandbox subcommands."""
    subcommand = args.subcommand

    # No subcommand → launch TUI
    if subcommand is None:
        _launch_sandbox_tui()
        return

    from rich.console import Console

    console = Console()

    providers, managers = _init_sandbox_providers()
    if not managers:
        console.print("[yellow]No sandbox providers configured.[/yellow]")
        console.print("Add config files to ~/.leon/sandboxes/ (see docs/SANDBOX.md)")
        return

    # Dispatch to handler
    handlers = {
        "ls": _cmd_sandbox_list,
        "list": _cmd_sandbox_list,
        "new": _cmd_sandbox_new,
        "rm": _cmd_sandbox_rm,
        "delete": _cmd_sandbox_rm,
        "pause": _cmd_sandbox_pause,
        "resume": _cmd_sandbox_resume,
        "metrics": _cmd_sandbox_metrics,
        "destroy-all-sessions": _cmd_sandbox_destroy_all,
    }

    handler = handlers.get(subcommand)
    if handler:
        handler(args, console, providers, managers)
    else:
        console.print(f"[red]Unknown subcommand: {subcommand}[/red]")
        console.print("Available: ls, new, rm, pause, resume, metrics, destroy-all-sessions")


def _launch_sandbox_tui() -> None:
    """Launch sandbox manager TUI"""
    import os
    import sys

    api_key = os.getenv("AGENTBAY_API_KEY")
    try:
        from tui.widgets.sandbox_manager import SandboxManagerApp

        SandboxManagerApp(api_key=api_key).run()
    except ImportError as e:
        print(f"Failed to import sandbox manager: {e}")
        sys.exit(1)


def _cmd_sandbox_list(args, console, providers, managers) -> None:
    """List all sandbox sessions"""
    from rich.table import Table

    sessions = _load_all_sessions(managers)
    if not sessions:
        console.print("[yellow]No active sessions.[/yellow]")
        return

    table = Table(title="Sandbox Sessions")
    table.add_column("Session ID", style="cyan")
    table.add_column("Status", style="green")
    table.add_column("Provider", style="magenta")
    table.add_column("Thread", style="white")

    for s in sessions:
        status_style = {"running": "green", "paused": "yellow"}.get(s["status"], "red")
        table.add_row(s["id"], f"[{status_style}]{s['status']}[/{status_style}]", s["provider"], s["thread"])

    console.print(table)


def _cmd_sandbox_new(args, console, providers, managers) -> None:
    """Create new sandbox session"""
    import os

    provider_name = args.extra_args[0] if args.extra_args else None
    if not provider_name:
        # Pick first available
        for name in ("agentbay", "e2b", "docker", "daytona"):
            if name in managers:
                provider_name = name
                break

    if not provider_name or provider_name not in managers:
        console.print(f"[red]Provider not available: {provider_name or 'none'}[/red]")
        console.print(f"Available: {', '.join(managers.keys())}")
        return

    manager = managers[provider_name]
    thread_id = f"sandbox-{os.urandom(4).hex()}"

    try:
        info = manager.get_or_create_session(thread_id)
        console.print(f"[green]Created {provider_name} session:[/green] {info.session_id}")
        console.print(f"  Thread: {thread_id}")
    except Exception as e:
        console.print(f"[red]Failed to create session: {e}[/red]")


def _cmd_sandbox_rm(args, console, providers, managers) -> None:
    """Delete sandbox session"""
    if not args.extra_args:
        console.print("Usage: leonai sandbox rm <session_id>")
        return

    sessions = _load_all_sessions(managers)
    target = _find_session(sessions, args.extra_args[0])
    if not target:
        console.print(f"[red]Session not found: {args.extra_args[0]}[/red]")
        return

    manager = managers.get(target["provider"])
    if not manager:
        console.print("[red]Provider unavailable[/red]")
        return

    if manager.destroy_session(thread_id=target["thread"], session_id=target["id"]):
        console.print(f"[green]Deleted:[/green] {target['id']}")
    else:
        console.print("[red]Delete failed[/red]")


def _cmd_sandbox_pause(args, console, providers, managers) -> None:
    """Pause sandbox session"""
    if not args.extra_args:
        console.print("Usage: leonai sandbox pause <session_id>")
        return

    sessions = _load_all_sessions(managers)
    target = _find_session(sessions, args.extra_args[0])
    if not target:
        console.print(f"[red]Session not found: {args.extra_args[0]}[/red]")
        return

    manager = managers.get(target["provider"])
    try:
        if manager and manager.pause_session(target["thread"]):
            console.print(f"[green]Paused:[/green] {target['id']}")
        else:
            console.print("[red]Pause failed[/red]")
    except Exception as e:
        console.print(f"[red]Pause failed: {e}[/red]")


def _cmd_sandbox_resume(args, console, providers, managers) -> None:
    """Resume sandbox session"""
    if not args.extra_args:
        console.print("Usage: leonai sandbox resume <session_id>")
        return

    sessions = _load_all_sessions(managers)
    target = _find_session(sessions, args.extra_args[0])
    if not target:
        console.print(f"[red]Session not found: {args.extra_args[0]}[/red]")
        return

    manager = managers.get(target["provider"])
    try:
        if manager and manager.resume_session(target["thread"]):
            console.print(f"[green]Resumed:[/green] {target['id']}")
        else:
            console.print("[red]Resume failed[/red]")
    except Exception as e:
        console.print(f"[red]Resume failed: {e}[/red]")


def _cmd_sandbox_metrics(args, console, providers, managers) -> None:
    """Show sandbox metrics"""
    if not args.extra_args:
        console.print("Usage: leonai sandbox metrics <session_id>")
        return

    sessions = _load_all_sessions(managers)
    target = _find_session(sessions, args.extra_args[0])
    if not target:
        console.print(f"[red]Session not found: {args.extra_args[0]}[/red]")
        return

    provider = providers.get(target["provider"])
    if not provider:
        console.print("[red]Provider unavailable[/red]")
        return

    try:
        metrics = provider.get_metrics(target["id"])
        if metrics:
            console.print(f"[bold]Session:[/bold] {target['id']}")
            console.print(f"  CPU:     {metrics.cpu_percent:.1f}%")
            console.print(f"  Memory:  {metrics.memory_used_mb:.0f}MB / {metrics.memory_total_mb:.0f}MB")
            console.print(f"  Disk:    {metrics.disk_used_gb:.1f}GB / {metrics.disk_total_gb:.1f}GB")
            console.print(f"  Network: RX {metrics.network_rx_kbps:.1f} KB/s | TX {metrics.network_tx_kbps:.1f} KB/s")
            if target["provider"] == "agentbay":
                url = provider.get_web_url(target["id"])
                if url:
                    console.print(f"  URL:     {url}")
        else:
            console.print("[yellow]Metrics not available for this provider.[/yellow]")
    except Exception as e:
        console.print(f"[red]Failed to get metrics: {e}[/red]")


def _cmd_sandbox_destroy_all(args, console, providers, managers) -> None:
    """Destroy all sandbox sessions"""
    from concurrent.futures import ThreadPoolExecutor

    sessions = _load_all_sessions(managers)
    if not sessions:
        console.print("[yellow]No active sessions.[/yellow]")
        return

    console.print(f"[bold red]This will destroy {len(sessions)} session(s):[/bold red]")
    for s in sessions:
        console.print(f"  {s['id']}  ({s['provider']}, {s['status']})")

    confirm = input("\nType 'yes' to confirm: ")
    if confirm != "yes":
        console.print("[yellow]Cancelled.[/yellow]")
        return

    def _destroy(s):
        mgr = managers.get(s["provider"])
        if mgr:
            mgr.destroy_session(thread_id=s["thread"], session_id=s["id"])
        return s["id"]

    with ThreadPoolExecutor(max_workers=min(len(sessions), 8)) as pool:
        for sid in pool.map(_destroy, sessions):
            console.print(f"  [red]Destroyed:[/red] {sid}")

    console.print(f"[green]Done. {len(sessions)} session(s) destroyed.[/green]")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="Leon AI - 你的 AI 编程助手", add_help=False)
    parser.add_argument("--profile", type=str, help="Profile 配置文件路径")
    parser.add_argument("--model", type=str, help="模型名称（覆盖 profile 和环境变量）")
    parser.add_argument("--agent", type=str, default=None, help="Task Agent name (bash/explore/general/plan)")
    parser.add_argument("--workspace", type=str, help="工作目录")
    parser.add_argument("--sandbox", type=str, help="Sandbox 名称 (从 ~/.leon/sandboxes/<name>.json 加载，默认 local)")
    parser.add_argument("--thread", type=str, help="Thread ID (恢复对话)")
    parser.add_argument("-c", "--continue", dest="continue_last", action="store_true", help="继续上次对话")
    parser.add_argument("-h", "--help", action="store_true", help="显示帮助信息")
    parser.add_argument("command", nargs="?", help="命令 (config, thread)")
    parser.add_argument("subcommand", nargs="?", help="子命令")
    parser.add_argument("extra_args", nargs="*", help="额外参数")

    args, unknown = parser.parse_known_args()

    if args.help and not args.command:
        _show_main_help()
        return

    # Handle commands
    if args.command == "config":
        _handle_config_command(args)
        return

    if args.command == "thread":
        _handle_thread_command(args, unknown)
        return

    if args.command == "sandbox":
        _handle_sandbox_command(args)
        return

    if args.command == "run":
        _handle_run_command(args, unknown)
        return

    # Default: launch TUI
    _launch_tui(args)


def _show_main_help() -> None:
    """Show main help message"""
    print("Leon AI - 你的 AI 编程助手\n")
    print("用法:")
    print("  leonai                    启动 Leon (新对话)")
    print("  leonai -c                 继续上次对话")
    print("  leonai --model <name>     使用指定模型")
    print("  leonai --agent <name>     使用指定 agent 预设 (default/coder/researcher/tester)")
    print("  leonai --profile <path>   使用指定 profile 启动")
    print("  leonai --workspace <dir>  指定工作目录")
    print("  leonai --sandbox <name>   使用指定 sandbox 配置")
    print("  leonai --thread <id>      恢复指定对话")
    print("  leonai config             配置 API key 和其他设置")
    print("  leonai config show        显示当前配置")
    print()
    print("非交互式运行:")
    print('  leonai run "消息"         发送单条消息')
    print("  leonai run --stdin        从 stdin 读取消息（空行分隔）")
    print("  leonai run -i             交互模式（无 TUI）")
    print("  leonai run -d             带 debug 输出")
    print()
    print("Thread 管理:")
    print("  leonai thread ls          列出所有对话")
    print("  leonai thread list        列出所有对话")
    print("  leonai thread history <thread_id>   查看对话历史")
    print("  leonai thread rewind <thread_id> <checkpoint_id>  回退到指定节点")
    print("  leonai thread rm <thread_id>        删除对话")
    print()
    print("Sandbox 管理:")
    print("  leonai sandbox            打开 sandbox 会话管理器 (TUI)")
    print("  leonai sandbox ls         列出所有 sandbox 会话")
    print("  leonai sandbox new [provider]  创建新会话 (agentbay/e2b/docker/daytona)")
    print("  leonai sandbox pause <id>      暂停会话")
    print("  leonai sandbox resume <id>     恢复会话")
    print("  leonai sandbox rm <id>         删除会话")
    print("  leonai sandbox metrics <id>    查看会话资源指标")


def _handle_config_command(args) -> None:
    """Handle config command"""
    if args.subcommand == "show":
        show_config()
    else:
        interactive_config()


def _handle_thread_command(args, unknown: list[str]) -> None:
    """Handle thread command"""
    subcommand = args.subcommand

    if subcommand in ("ls", "list", None):
        cmd_thread_list(args)
    elif subcommand == "history":
        if not args.extra_args:
            print("用法: leonai thread history <thread_id>")
            sys.exit(1)
        args.thread_id = args.extra_args[0]
        cmd_thread_history(args)
    elif subcommand == "rewind":
        if len(args.extra_args) < 2:
            print("用法: leonai thread rewind <thread_id> <checkpoint_id> [-y]")
            sys.exit(1)
        args.thread_id = args.extra_args[0]
        args.checkpoint_id = args.extra_args[1]
        args.yes = "-y" in unknown or "--yes" in unknown
        cmd_thread_rewind(args)
    elif subcommand == "rm":
        if not args.extra_args:
            print("用法: leonai thread rm <thread_id> [-y]")
            sys.exit(1)
        args.thread_id = args.extra_args[0]
        args.yes = "-y" in unknown or "--yes" in unknown
        cmd_thread_rm(args)
    else:
        print(f"未知子命令: {subcommand}")
        print("可用子命令: ls, list, history, rewind, rm")
        sys.exit(1)


def _handle_sandbox_command(args) -> None:
    """Handle sandbox command"""
    config_manager = ConfigManager()
    config_manager.load_to_env()
    cmd_sandbox(args)


def _handle_run_command(args, unknown: list[str]) -> None:
    """Handle run command"""
    from tui.runner import cmd_run

    cmd_run(args, unknown)


def _launch_tui(args) -> None:
    """Launch TUI mode"""
    config_manager = ConfigManager()
    config_manager.load_to_env()

    if not os.getenv("OPENAI_API_KEY") and not os.getenv("ANTHROPIC_API_KEY"):
        print("⚠️  未检测到 API Key，进入配置向导...\n")
        interactive_config()
        config_manager.load_to_env()
        if not os.getenv("OPENAI_API_KEY"):
            print("\n❌ 配置未完成，退出")
            sys.exit(1)
        print()

    workspace = Path(args.workspace) if args.workspace else Path.cwd()
    model_name = getattr(args, "model", None) or os.getenv("MODEL_NAME") or None

    from agent import create_leon_agent
    from tui.app import run_tui

    session_mgr = SessionManager()

    # Resolve thread_id
    thread_id = _resolve_thread_id(args, session_mgr)

    # Auto-detect sandbox when resuming
    sandbox_arg = _auto_detect_sandbox(args, thread_id)

    print("🚀 初始化 Leon Agent...")

    try:
        agent = create_leon_agent(
            model_name=model_name or DEFAULT_MODEL,
            profile=args.profile,
            workspace_root=workspace,
            sandbox=sandbox_arg,
            agent=args.agent,
            verbose=False,
        )
    except Exception as e:
        print(f"❌ 初始化失败: {e}")
        sys.exit(1)

    print("✅ Agent 已就绪")
    print(f"📁 工作目录: {agent.workspace_root}\n")

    try:
        run_tui(agent, agent.workspace_root, thread_id, session_mgr)
    except KeyboardInterrupt:
        print("\n\n👋 再见！")
    finally:
        session_mgr.save_session(thread_id, str(workspace))
        agent.close()
        print("\n🧹 已退出")


def _resolve_thread_id(args, session_mgr: SessionManager) -> str:
    """Resolve thread ID from args or create new one"""
    if args.thread:
        print(f"📝 恢复对话: {args.thread}")
        return args.thread

    if args.continue_last:
        last_thread = session_mgr.get_last_thread_id()
        if last_thread:
            print(f"📝 继续上次对话: {last_thread}")
            return last_thread

    thread_id = f"tui-{uuid.uuid4().hex[:8]}"
    print(f"📝 新对话: {thread_id}")
    return thread_id


def _auto_detect_sandbox(args, thread_id: str) -> str | None:
    """Auto-detect sandbox when resuming a thread"""
    sandbox_arg = getattr(args, "sandbox", None)
    if not sandbox_arg and (args.thread or args.continue_last):
        from sandbox.manager import lookup_sandbox_for_thread

        detected = lookup_sandbox_for_thread(thread_id)
        if detected:
            config_path = Path.home() / ".leon" / "sandboxes" / f"{detected}.json"
            if config_path.exists():
                print(f"🔄 Auto-detected sandbox: {detected}")
                return detected
    return sandbox_arg


if __name__ == "__main__":
    main()
