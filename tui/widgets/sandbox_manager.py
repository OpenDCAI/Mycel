"""
Sandbox Session Manager TUI.

Lists all sandbox sessions with actions: create, delete, pause, resume, metrics.
Launch with: leonai sandbox
"""

import os
from pathlib import Path

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, DataTable, Footer, Header, Static

from sandbox.config import SandboxConfig
from sandbox.manager import SandboxManager


class SandboxManagerApp(App):
    """TUI for managing sandbox sessions."""

    CSS = """
    #main { height: 1fr; }
    #sidebar { width: 20; border: solid green; }
    #content { border: solid blue; padding: 1; }
    #detail { height: 10; border: solid magenta; padding: 1; }
    #status { height: 3; border: solid yellow; padding: 0 1; }
    Button { margin: 0; width: 100%; }
    Button.muted { opacity: 0.5; }
    DataTable { height: 100%; }
    """

    BINDINGS = [
        Binding("r", "refresh", "Refresh"),
        Binding("d", "delete_session", "Delete"),
        Binding("n", "new_session", "New"),
        Binding("p", "pause_session", "Pause"),
        Binding("u", "resume_session", "Resume"),
        Binding("m", "show_metrics", "Metrics"),
        Binding("o", "open_url", "Open URL"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self, api_key: str | None):
        super().__init__()
        self._providers = self._init_providers(api_key)
        self._managers = {name: SandboxManager(provider=provider) for name, provider in self._providers.items()}
        self.sessions: list[dict] = []
        self._pause_resume_support_by_session: dict[str, bool] = {}

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="main"):
            with VerticalScroll(id="sidebar"):
                yield Button("Refresh", id="btn-refresh", variant="primary")
                yield Button("New", id="btn-new", variant="success")
                yield Button("Delete", id="btn-delete", variant="error")
                yield Button("Pause", id="btn-pause", variant="warning")
                yield Button("Resume", id="btn-resume", variant="success")
                yield Button("Metrics", id="btn-metrics", variant="primary")
                yield Button("Open URL", id="btn-url", variant="primary")
            with Vertical(id="content"):
                yield DataTable(id="table")
        yield Static("Select a session to view details", id="detail")
        yield Static("Ready - Press R to refresh", id="status")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#table", DataTable)
        table.add_columns("Session ID", "Status", "Provider", "Thread")
        table.cursor_type = "row"
        self.do_refresh()

    def set_status(self, msg: str) -> None:
        self.query_one("#status", Static).update(msg)

    def _init_providers(self, api_key: str | None) -> dict[str, object]:
        """Load providers from ~/.leon/sandboxes/*.json config files."""
        providers: dict[str, object] = {}
        sandboxes_dir = Path.home() / ".leon" / "sandboxes"
        if not sandboxes_dir.exists():
            return providers

        for config_file in sandboxes_dir.glob("*.json"):
            name = config_file.stem
            try:
                config = SandboxConfig.load(name)
                if config.provider == "agentbay":
                    from sandbox.providers.agentbay import AgentBayProvider

                    key = config.agentbay.api_key or api_key or os.getenv("AGENTBAY_API_KEY")
                    if key:
                        providers["agentbay"] = AgentBayProvider(
                            api_key=key,
                            region_id=config.agentbay.region_id,
                            default_context_path=config.agentbay.context_path,
                            image_id=config.agentbay.image_id,
                        )
                elif config.provider == "docker":
                    from sandbox.providers.docker import DockerProvider

                    providers["docker"] = DockerProvider(
                        image=config.docker.image,
                        mount_path=config.docker.mount_path,
                        default_cwd=config.docker.cwd,
                        bind_mounts=config.docker.bind_mounts,
                    )
                elif config.provider == "e2b":
                    from sandbox.providers.e2b import E2BProvider

                    key = config.e2b.api_key or os.getenv("E2B_API_KEY")
                    if key:
                        providers["e2b"] = E2BProvider(
                            api_key=key,
                            template=config.e2b.template,
                            default_cwd=config.e2b.cwd,
                            timeout=config.e2b.timeout,
                        )
                elif config.provider == "daytona":
                    from sandbox.providers.daytona import DaytonaProvider

                    key = config.daytona.api_key or os.getenv("DAYTONA_API_KEY")
                    if key:
                        providers["daytona"] = DaytonaProvider(
                            api_key=key,
                            api_url=config.daytona.api_url,
                            target=config.daytona.target,
                            default_cwd=config.daytona.cwd,
                            bind_mounts=config.daytona.bind_mounts,
                        )
            except Exception as e:
                print(f"[SandboxManager] Failed to load {name}: {e}")

        return providers

    def action_refresh(self) -> None:
        self.do_refresh()

    @work(exclusive=True, thread=True)
    def do_refresh(self) -> None:
        self.call_from_thread(self.set_status, "Loading sessions...")
        sessions = self._load_sessions()
        self.call_from_thread(self._update_table, sessions)

    def _update_table(self, sessions: list[dict]) -> None:
        self.sessions = sessions
        table = self.query_one("#table", DataTable)
        table.clear()
        active_ids = set()
        for s in sessions:
            active_ids.add(s["id"])
            table.add_row(s["id"], s["status"], s["provider"], s["thread"])
        if self._pause_resume_support_by_session:
            self._pause_resume_support_by_session = {
                sid: supported for sid, supported in self._pause_resume_support_by_session.items() if sid in active_ids
            }
        self.set_status(f"Found {len(sessions)} session(s)")
        sid = self._get_selected_session(notify=False)
        if sid:
            self._apply_pause_resume_state(sid)

    def _load_sessions(self) -> list[dict]:
        sessions: list[dict] = []
        for manager in self._managers.values():
            for row in manager.list_sessions():
                sessions.append(
                    {
                        "id": row["session_id"],
                        "status": row["status"],
                        "provider": row["provider"],
                        "thread": row["thread_id"],
                    }
                )
        return sessions

    def _get_selected_session(self, notify: bool = True) -> str | None:
        table = self.query_one("#table", DataTable)
        if not self.sessions or table.cursor_row is None:
            if notify:
                self.set_status("No session selected")
            return None
        idx = table.cursor_row
        if idx >= len(self.sessions):
            return None
        return self.sessions[idx]["id"]

    def action_delete_session(self) -> None:
        sid = self._get_selected_session()
        if sid:
            self.do_delete(sid)

    @work(exclusive=True, thread=True)
    def do_delete(self, sid: str) -> None:
        self.call_from_thread(self.set_status, f"Deleting {sid[:16]}...")
        try:
            provider_name = self._get_provider_for_session(sid)
            if not provider_name:
                self.call_from_thread(self.set_status, "Session not found")
                return
            manager = self._managers[provider_name]
            thread_id = self._get_thread_for_session(sid)
            if manager.destroy_session(thread_id=thread_id or "", session_id=sid):
                self.call_from_thread(self.set_status, f"Deleted {sid[:16]}")
                self.do_refresh()
            else:
                self.call_from_thread(self.set_status, "Delete failed")
        except Exception as e:
            self.call_from_thread(self.set_status, f"Delete failed: {e}")

    def action_new_session(self) -> None:
        self.do_create()

    @work(exclusive=True, thread=True)
    def do_create(self) -> None:
        provider_name = self._default_provider_for_create()
        if not provider_name:
            self.call_from_thread(self.set_status, "No providers available")
            return
        self.call_from_thread(self.set_status, f"Creating new {provider_name} session...")
        try:
            manager = self._managers.get(provider_name)
            if not manager:
                self.call_from_thread(self.set_status, f"Provider not available: {provider_name}")
                return
            thread_id = f"sandbox-{os.urandom(4).hex()}"
            info = manager.get_or_create_session(thread_id)
            self.call_from_thread(self.set_status, f"Created: {info.session_id[:16]}")
            self.do_refresh()
        except Exception as e:
            self.call_from_thread(self.set_status, f"Create failed: {e}")

    @work(exclusive=True, thread=True)
    def do_pause(self, sid: str) -> None:
        self.call_from_thread(self.set_status, f"Pausing {sid[:16]}...")
        try:
            provider_name = self._get_provider_for_session(sid)
            if not provider_name:
                self.call_from_thread(self.set_status, "Session not found")
                return
            manager = self._managers[provider_name]
            thread_id = self._get_thread_for_session(sid)
            if thread_id and manager.pause_session(thread_id):
                self._pause_resume_support_by_session[sid] = True
                self.call_from_thread(self.set_status, f"Paused {sid[:16]}")
            else:
                self.call_from_thread(self.set_status, "Failed to pause")
            self.do_refresh()
        except Exception as e:
            if self._is_pause_resume_not_supported(e):
                self._pause_resume_support_by_session[sid] = False
                self.call_from_thread(self._apply_pause_resume_state, sid)
                self.call_from_thread(self.set_status, "Pause/resume not available (account tier)")
            else:
                self.call_from_thread(self.set_status, f"Pause failed: {e}")

    @work(exclusive=True, thread=True)
    def do_resume(self, sid: str) -> None:
        self.call_from_thread(self.set_status, f"Resuming {sid[:16]}...")
        try:
            provider_name = self._get_provider_for_session(sid)
            if not provider_name:
                self.call_from_thread(self.set_status, "Session not found")
                return
            manager = self._managers[provider_name]
            thread_id = self._get_thread_for_session(sid)
            if thread_id and manager.resume_session(thread_id):
                self._pause_resume_support_by_session[sid] = True
                self.call_from_thread(self.set_status, f"Resumed {sid[:16]}")
            else:
                self.call_from_thread(self.set_status, "Failed to resume")
            self.do_refresh()
        except Exception as e:
            if self._is_pause_resume_not_supported(e):
                self._pause_resume_support_by_session[sid] = False
                self.call_from_thread(self._apply_pause_resume_state, sid)
                self.call_from_thread(self.set_status, "Pause/resume not available (account tier)")
            else:
                self.call_from_thread(self.set_status, f"Resume failed: {e}")

    def action_show_metrics(self) -> None:
        sid = self._get_selected_session()
        if sid:
            self.do_get_metrics(sid)

    @work(exclusive=True, thread=True)
    def do_get_metrics(self, sid: str) -> None:
        self.call_from_thread(self.set_status, f"Getting metrics for {sid[:16]}...")
        try:
            provider_name = self._get_provider_for_session(sid)
            if not provider_name:
                self.call_from_thread(self._update_detail, "Session not found")
                return
            provider = self._providers.get(provider_name)
            if not provider:
                self.call_from_thread(self._update_detail, "Provider unavailable")
                return
            metrics = provider.get_metrics(sid)
            url = provider.get_web_url(sid) if provider_name == "agentbay" else None
            if metrics:
                detail = (
                    f"Session: {sid}\n"
                    f"CPU: {metrics.cpu_percent:.1f}%\n"
                    f"Memory: {metrics.memory_used_mb:.0f}MB / {metrics.memory_total_mb:.0f}MB\n"
                    f"Disk: {metrics.disk_used_gb:.1f}GB / {metrics.disk_total_gb:.1f}GB\n"
                    f"Network: RX {metrics.network_rx_kbps:.1f} KB/s | TX {metrics.network_tx_kbps:.1f} KB/s\n"
                )
                if url:
                    detail += f"\nWeb URL: {url[:60]}..."
                self.call_from_thread(self._update_detail, detail)
                self.call_from_thread(self.set_status, "Metrics loaded")
            else:
                self.call_from_thread(self._update_detail, "Metrics unavailable")
                self.call_from_thread(self.set_status, "Failed to get metrics")
        except Exception as e:
            self.call_from_thread(self._update_detail, f"Error: {e}")
            self.call_from_thread(self.set_status, f"Error: {e}")

    def action_open_url(self) -> None:
        sid = self._get_selected_session()
        if sid:
            self.do_open_url(sid)

    @work(exclusive=True, thread=True)
    def do_open_url(self, sid: str) -> None:
        self.call_from_thread(self.set_status, f"Getting URL for {sid[:16]}...")
        try:
            provider_name = self._get_provider_for_session(sid)
            if provider_name != "agentbay":
                self.call_from_thread(self.set_status, "No URL available")
                return
            provider = self._providers.get(provider_name)
            if not provider:
                self.call_from_thread(self.set_status, "Provider unavailable")
                return
            url = provider.get_web_url(sid)
            if url:
                import webbrowser

                webbrowser.open(url)
                self.call_from_thread(self.set_status, "Opened in browser")
            else:
                self.call_from_thread(self.set_status, "No URL available")
        except Exception as e:
            self.call_from_thread(self.set_status, f"Error: {e}")

    def _update_detail(self, text: str) -> None:
        self.query_one("#detail", Static).update(text)

    def _is_pause_resume_not_supported(self, result_or_error: object) -> bool:
        code = getattr(result_or_error, "code", "") or getattr(result_or_error, "error_code", "")
        if code == "BenefitLevel.NotSupport":
            return True
        message = (
            getattr(result_or_error, "error_message", "")
            or getattr(result_or_error, "message", "")
            or str(result_or_error)
        )
        return "BenefitLevel.NotSupport" in message

    def _mute_pause_resume(self) -> None:
        pause_btn = self.query_one("#btn-pause", Button)
        resume_btn = self.query_one("#btn-resume", Button)
        pause_btn.add_class("muted")
        resume_btn.add_class("muted")
        pause_btn.label = "Pause (N/A)"
        resume_btn.label = "Resume (N/A)"

    def _unmute_pause_resume(self) -> None:
        pause_btn = self.query_one("#btn-pause", Button)
        resume_btn = self.query_one("#btn-resume", Button)
        pause_btn.remove_class("muted")
        resume_btn.remove_class("muted")
        pause_btn.label = "Pause"
        resume_btn.label = "Resume"

    def _apply_pause_resume_state(self, sid: str) -> None:
        if self._pause_resume_support_by_session.get(sid) is False:
            self._mute_pause_resume()
        else:
            self._unmute_pause_resume()

    def action_pause_session(self) -> None:
        sid = self._get_selected_session()
        if sid:
            if self._pause_resume_support_by_session.get(sid) is False:
                self.set_status("Pause not available (account tier)")
                return
            self.do_pause(sid)

    def action_resume_session(self) -> None:
        sid = self._get_selected_session()
        if sid:
            if self._pause_resume_support_by_session.get(sid) is False:
                self.set_status("Resume not available (account tier)")
                return
            self.do_resume(sid)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        actions = {
            "btn-refresh": self.action_refresh,
            "btn-new": self.action_new_session,
            "btn-delete": self.action_delete_session,
            "btn-pause": self.action_pause_session,
            "btn-resume": self.action_resume_session,
            "btn-metrics": self.action_show_metrics,
            "btn-url": self.action_open_url,
        }
        action = actions.get(event.button.id)
        if action:
            action()

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        sid = self._get_selected_session(notify=False)
        if sid:
            self._apply_pause_resume_state(sid)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        sid = self._get_selected_session(notify=False)
        if sid:
            self._apply_pause_resume_state(sid)

    def _get_provider_for_session(self, session_id: str) -> str | None:
        for s in self.sessions:
            if s["id"] == session_id:
                return s["provider"]
        return None

    def _get_thread_for_session(self, session_id: str) -> str | None:
        for s in self.sessions:
            if s["id"] == session_id:
                return s["thread"]
        return None

    def _default_provider_for_create(self) -> str | None:
        for name in ("agentbay", "e2b", "docker", "daytona"):
            if name in self._managers:
                return name
        return None
