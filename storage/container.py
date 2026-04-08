"""Storage container — Supabase-only repo composition root."""

from __future__ import annotations

import importlib
from typing import Any

from .contracts import (
    AgentConfigRepo,
    AgentRegistryRepo,
    ChatRepo,
    ChatSessionRepo,
    CheckpointRepo,
    ContactRepo,
    CronJobRepo,
    EvalRepo,
    FileOperationRepo,
    InviteCodeRepo,
    LeaseRepo,
    PanelTaskRepo,
    ProviderEventRepo,
    QueueRepo,
    RecipeRepo,
    ResourceSnapshotRepo,
    RunEventRepo,
    SandboxVolumeRepo,
    SummaryRepo,
    SyncFileRepo,
    TerminalRepo,
    ThreadLaunchPrefRepo,
    ThreadRepo,
    ToolTaskRepo,
    UserRepo,
    UserSettingsRepo,
)

_REPO_REGISTRY: dict[str, tuple[str, str]] = {
    "checkpoint_repo": ("storage.providers.supabase.checkpoint_repo", "SupabaseCheckpointRepo"),
    "run_event_repo": ("storage.providers.supabase.run_event_repo", "SupabaseRunEventRepo"),
    "file_operation_repo": ("storage.providers.supabase.file_operation_repo", "SupabaseFileOperationRepo"),
    "summary_repo": ("storage.providers.supabase.summary_repo", "SupabaseSummaryRepo"),
    "eval_repo": ("storage.providers.supabase.eval_repo", "SupabaseEvalRepo"),
    "queue_repo": ("storage.providers.supabase.queue_repo", "SupabaseQueueRepo"),
    "sandbox_volume_repo": ("storage.providers.supabase.sandbox_volume_repo", "SupabaseSandboxVolumeRepo"),
    "provider_event_repo": ("storage.providers.supabase.provider_event_repo", "SupabaseProviderEventRepo"),
    "lease_repo": ("storage.providers.supabase.lease_repo", "SupabaseLeaseRepo"),
    "terminal_repo": ("storage.providers.supabase.terminal_repo", "SupabaseTerminalRepo"),
    "chat_session_repo": ("storage.providers.supabase.chat_session_repo", "SupabaseChatSessionRepo"),
    "panel_task_repo": ("storage.providers.supabase.panel_task_repo", "SupabasePanelTaskRepo"),
    "cron_job_repo": ("storage.providers.supabase.cron_job_repo", "SupabaseCronJobRepo"),
    "agent_registry_repo": ("storage.providers.supabase.agent_registry_repo", "SupabaseAgentRegistryRepo"),
    "tool_task_repo": ("storage.providers.supabase.tool_task_repo", "SupabaseToolTaskRepo"),
    "sync_file_repo": ("storage.providers.supabase.sync_file_repo", "SupabaseSyncFileRepo"),
    "resource_snapshot_repo": ("storage.providers.supabase.resource_snapshot_repo", "SupabaseResourceSnapshotRepo"),
    "user_repo": ("storage.providers.supabase.user_repo", "SupabaseUserRepo"),
    "thread_repo": ("storage.providers.supabase.thread_repo", "SupabaseThreadRepo"),
    "thread_launch_pref_repo": ("storage.providers.supabase.thread_launch_pref_repo", "SupabaseThreadLaunchPrefRepo"),
    "recipe_repo": ("storage.providers.supabase.recipe_repo", "SupabaseRecipeRepo"),
    "chat_repo": ("storage.providers.supabase.chat_repo", "SupabaseChatRepo"),
    "invite_code_repo": ("storage.providers.supabase.invite_code_repo", "SupabaseInviteCodeRepo"),
    "user_settings_repo": ("storage.providers.supabase.user_settings_repo", "SupabaseUserSettingsRepo"),
    "agent_config_repo": ("storage.providers.supabase.agent_config_repo", "SupabaseAgentConfigRepo"),
    "contact_repo": ("storage.providers.supabase.contact_repo", "SupabaseContactRepo"),
}


class StorageContainer:
    """Composition root for storage repos (Supabase-only)."""

    def __init__(self, supabase_client: Any, public_supabase_client: Any | None = None, **_kwargs: Any) -> None:
        if supabase_client is None:
            raise RuntimeError("StorageContainer requires a supabase_client.")
        self._supabase_client = supabase_client
        self._public_supabase_client = public_supabase_client or supabase_client

    def _build(self, name: str, *, client: Any | None = None) -> Any:
        mod_path, cls_name = _REPO_REGISTRY[name]
        mod = importlib.import_module(mod_path)
        return getattr(mod, cls_name)(client=client or self._supabase_client)

    def checkpoint_repo(self) -> CheckpointRepo:
        return self._build("checkpoint_repo")

    def run_event_repo(self) -> RunEventRepo:
        return self._build("run_event_repo")

    def file_operation_repo(self) -> FileOperationRepo:
        return self._build("file_operation_repo")

    def summary_repo(self) -> SummaryRepo:
        return self._build("summary_repo")

    def queue_repo(self) -> QueueRepo:
        return self._build("queue_repo")

    def eval_repo(self) -> EvalRepo:
        return self._build("eval_repo")

    def sandbox_volume_repo(self) -> SandboxVolumeRepo:
        return self._build("sandbox_volume_repo")

    def provider_event_repo(self) -> ProviderEventRepo:
        return self._build("provider_event_repo")

    def lease_repo(self) -> LeaseRepo:
        return self._build("lease_repo")

    def terminal_repo(self) -> TerminalRepo:
        return self._build("terminal_repo")

    def chat_session_repo(self) -> ChatSessionRepo:
        return self._build("chat_session_repo")

    def panel_task_repo(self) -> PanelTaskRepo:
        # @@@panel-task-public-schema - panel task board is still a public-schema
        # island, so the live repo must not silently inherit runtime staging schema.
        return self._build("panel_task_repo", client=self._public_supabase_client)

    def cron_job_repo(self) -> CronJobRepo:
        return self._build("cron_job_repo")

    def agent_registry_repo(self) -> AgentRegistryRepo:
        return self._build("agent_registry_repo")

    def tool_task_repo(self) -> ToolTaskRepo:
        return self._build("tool_task_repo")

    def sync_file_repo(self) -> SyncFileRepo:
        # @@@sync-file-public-schema - sync_files is still a public-schema island,
        # so runtime cleanup must not silently inherit staging.
        return self._build("sync_file_repo", client=self._public_supabase_client)

    def resource_snapshot_repo(self) -> ResourceSnapshotRepo:
        return self._build("resource_snapshot_repo")

    def user_repo(self) -> UserRepo:
        return self._build("user_repo")

    def thread_repo(self) -> ThreadRepo:
        return self._build("thread_repo")

    def thread_launch_pref_repo(self) -> ThreadLaunchPrefRepo:
        return self._build("thread_launch_pref_repo")

    def recipe_repo(self) -> RecipeRepo:
        return self._build("recipe_repo")

    def chat_repo(self) -> ChatRepo:
        return self._build("chat_repo")

    def invite_code_repo(self) -> InviteCodeRepo:
        return self._build("invite_code_repo")

    def user_settings_repo(self) -> UserSettingsRepo:
        # @@@user-settings-public-schema - user_settings is still a public-schema
        # island, so authenticated settings routes must not inherit staging.
        return self._build("user_settings_repo", client=self._public_supabase_client)

    def agent_config_repo(self) -> AgentConfigRepo:
        return self._build("agent_config_repo")

    def contact_repo(self) -> ContactRepo:
        return self._build("contact_repo")

    def purge_thread(self, thread_id: str) -> None:
        """Delete all data for a thread across all repos."""
        checkpoint = self.checkpoint_repo()
        try:
            checkpoint.delete_thread_data(thread_id)
        finally:
            checkpoint.close()

        run_event = self.run_event_repo()
        try:
            run_event.delete_thread_events(thread_id)
        finally:
            run_event.close()

        file_op = self.file_operation_repo()
        try:
            file_op.delete_thread_operations(thread_id)
        finally:
            file_op.close()

        summary = self.summary_repo()
        try:
            summary.delete_thread_summaries(thread_id)
        finally:
            summary.close()
