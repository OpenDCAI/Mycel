"""Storage container — Supabase-only repo composition root."""

from __future__ import annotations

import importlib
from typing import Any

from .contracts import (
    ChatSessionRepo,
    CheckpointRepo,
    EvalRepo,
    FileOperationRepo,
    LeaseRepo,
    ProviderEventRepo,
    QueueRepo,
    RunEventRepo,
    SandboxVolumeRepo,
    SummaryRepo,
    TerminalRepo,
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
}


class StorageContainer:
    """Composition root for storage repos (Supabase-only)."""

    def __init__(self, supabase_client: Any, **_kwargs: Any) -> None:
        if supabase_client is None:
            raise RuntimeError("StorageContainer requires a supabase_client.")
        self._supabase_client = supabase_client

    def _build(self, name: str) -> Any:
        mod_path, cls_name = _REPO_REGISTRY[name]
        mod = importlib.import_module(mod_path)
        return getattr(mod, cls_name)(client=self._supabase_client)

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
