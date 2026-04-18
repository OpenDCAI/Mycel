"""Storage container — Supabase-only repo composition root."""

from __future__ import annotations

import importlib
from typing import Any

from .contracts import (
    AgentConfigRepo,
    ChatRepo,
    CheckpointRepo,
    ContactRepo,
    EvalRepo,
    EvaluationBatchRepo,
    FileOperationRepo,
    InviteCodeRepo,
    LeaseRepo,
    ProviderEventRepo,
    QueueRepo,
    RecipeRepo,
    ResourceSnapshotRepo,
    RunEventRepo,
    SandboxRepo,
    SummaryRepo,
    ThreadRepo,
    ToolTaskRepo,
    UserRepo,
    UserSettingsRepo,
    WorkspaceRepo,
)

_REPO_REGISTRY: dict[str, tuple[str, str]] = {
    "checkpoint_repo": ("storage.providers.supabase.checkpoint_repo", "SupabaseCheckpointRepo"),
    "run_event_repo": ("storage.providers.supabase.run_event_repo", "SupabaseRunEventRepo"),
    "schedule_repo": ("storage.providers.supabase.schedule_repo", "SupabaseScheduleRepo"),
    "file_operation_repo": ("storage.providers.supabase.file_operation_repo", "SupabaseFileOperationRepo"),
    "summary_repo": ("storage.providers.supabase.summary_repo", "SupabaseSummaryRepo"),
    "eval_repo": ("storage.providers.supabase.eval_repo", "SupabaseEvalRepo"),
    "evaluation_batch_repo": ("storage.providers.supabase.eval_batch_repo", "SupabaseEvaluationBatchRepo"),
    "queue_repo": ("storage.providers.supabase.queue_repo", "SupabaseQueueRepo"),
    "provider_event_repo": ("storage.providers.supabase.provider_event_repo", "SupabaseProviderEventRepo"),
    "lease_repo": ("storage.providers.supabase.lease_repo", "SupabaseLeaseRepo"),
    "tool_task_repo": ("storage.providers.supabase.tool_task_repo", "SupabaseToolTaskRepo"),
    "resource_snapshot_repo": ("storage.providers.supabase.resource_snapshot_repo", "SupabaseResourceSnapshotRepo"),
    "user_repo": ("storage.providers.supabase.user_repo", "SupabaseUserRepo"),
    "thread_repo": ("storage.providers.supabase.thread_repo", "SupabaseThreadRepo"),
    "workspace_repo": ("storage.providers.supabase.workspace_repo", "SupabaseWorkspaceRepo"),
    "sandbox_repo": ("storage.providers.supabase.sandbox_repo", "SupabaseSandboxRepo"),
    "recipe_repo": ("storage.providers.supabase.recipe_repo", "SupabaseRecipeRepo"),
    "chat_repo": ("storage.providers.supabase.chat_repo", "SupabaseChatRepo"),
    "chat_member_repo": ("storage.providers.supabase.messaging_repo", "SupabaseChatMemberRepo"),
    "messages_repo": ("storage.providers.supabase.messaging_repo", "SupabaseMessagesRepo"),
    "relationship_repo": ("storage.providers.supabase.messaging_repo", "SupabaseRelationshipRepo"),
    "invite_code_repo": ("storage.providers.supabase.invite_code_repo", "SupabaseInviteCodeRepo"),
    "user_settings_repo": ("storage.providers.supabase.user_settings_repo", "SupabaseUserSettingsRepo"),
    "agent_config_repo": ("storage.providers.supabase.agent_config_repo", "SupabaseAgentConfigRepo"),
    "contact_repo": ("storage.providers.supabase.contact_repo", "SupabaseContactRepo"),
}


class StorageContainer:
    """Composition root for storage repos (Supabase-only)."""

    def __init__(self, supabase_client: Any, public_supabase_client: Any | None = None) -> None:
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

    def schedule_repo(self) -> Any:
        return self._build("schedule_repo")

    def file_operation_repo(self) -> FileOperationRepo:
        return self._build("file_operation_repo")

    def summary_repo(self) -> SummaryRepo:
        return self._build("summary_repo")

    def queue_repo(self) -> QueueRepo:
        return self._build("queue_repo")

    def eval_repo(self) -> EvalRepo:
        return self._build("eval_repo")

    def evaluation_batch_repo(self) -> EvaluationBatchRepo:
        return self._build("evaluation_batch_repo")

    def provider_event_repo(self) -> ProviderEventRepo:
        return self._build("provider_event_repo")

    def lease_repo(self) -> LeaseRepo:
        return self._build("lease_repo")

    def tool_task_repo(self) -> ToolTaskRepo:
        return self._build("tool_task_repo")

    def resource_snapshot_repo(self) -> ResourceSnapshotRepo:
        return self._build("resource_snapshot_repo")

    def user_repo(self) -> UserRepo:
        return self._build("user_repo")

    def thread_repo(self) -> ThreadRepo:
        return self._build("thread_repo")

    def workspace_repo(self) -> WorkspaceRepo:
        return self._build("workspace_repo")

    def sandbox_repo(self) -> SandboxRepo:
        return self._build("sandbox_repo")

    def recipe_repo(self) -> RecipeRepo:
        return self._build("recipe_repo")

    def chat_repo(self) -> ChatRepo:
        return self._build("chat_repo")

    def chat_member_repo(self) -> Any:
        return self._build("chat_member_repo")

    def messages_repo(self) -> Any:
        return self._build("messages_repo")

    def relationship_repo(self) -> Any:
        return self._build("relationship_repo")

    def invite_code_repo(self) -> InviteCodeRepo:
        return self._build("invite_code_repo")

    def user_settings_repo(self) -> UserSettingsRepo:
        return self._build("user_settings_repo")

    def agent_config_repo(self) -> AgentConfigRepo:
        return self._build("agent_config_repo")

    def contact_repo(self) -> ContactRepo:
        return self._build("contact_repo")

    def purge_thread(self, thread_id: str) -> None:
        """Delete all data for a thread across all repos."""
        for repo_factory, purge in (
            (self.checkpoint_repo, lambda repo: repo.delete_thread_data(thread_id)),
            (self.run_event_repo, lambda repo: repo.delete_thread_events(thread_id)),
            (self.file_operation_repo, lambda repo: repo.delete_thread_operations(thread_id)),
            (self.summary_repo, lambda repo: repo.delete_thread_summaries(thread_id)),
        ):
            repo = repo_factory()
            try:
                purge(repo)
            finally:
                repo.close()
