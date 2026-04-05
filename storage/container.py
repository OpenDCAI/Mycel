"""Storage container with repo-level provider selection."""

from __future__ import annotations

import importlib
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

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

StorageStrategy = Literal["sqlite", "supabase"]
RepoProviderMap = Mapping[str, str]

# @@@repo-registry - maps repo name → (supabase module path, class name) for generic dispatch.
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
    """Composition root for storage repos."""

    _SUPPORTED_STRATEGIES = {"sqlite", "supabase"}
    _REPO_NAMES = (
        "checkpoint_repo",
        "run_event_repo",
        "file_operation_repo",
        "summary_repo",
        "eval_repo",
        "queue_repo",
        "sandbox_volume_repo",
        "provider_event_repo",
        "lease_repo",
        "terminal_repo",
        "chat_session_repo",
    )

    def __init__(
        self,
        main_db_path: str | Path | None = None,
        eval_db_path: str | Path | None = None,
        strategy: StorageStrategy = "sqlite",
        repo_providers: RepoProviderMap | None = None,
        supabase_bindings: Mapping[str, Any] | None = None,
        supabase_client: Any | None = None,
    ) -> None:
        if strategy not in self._SUPPORTED_STRATEGIES:
            raise ValueError(
                f"Unsupported storage strategy: {strategy}. "
                f"Supported strategies: {', '.join(sorted(self._SUPPORTED_STRATEGIES))}"
            )
        root = Path.home() / ".leon"
        self._main_db = Path(main_db_path) if main_db_path else root / "leon.db"
        self._queue_db = self._main_db.with_name("queue.db")
        self._run_event_db = self._main_db.with_name("events.db")
        self._file_op_db = self._main_db.with_name("file_ops.db")
        self._summary_db = self._main_db.with_name("summary.db")
        self._eval_db = Path(eval_db_path) if eval_db_path else root / "eval.db"
        self._sandbox_db = self._main_db.with_name("sandbox.db")
        self._strategy: StorageStrategy = strategy
        self._supabase_client = supabase_client
        self._repo_providers = self._resolve_repo_providers(
            default_strategy=strategy,
            repo_providers=repo_providers,
            legacy_supabase_bindings=supabase_bindings,
        )

    def checkpoint_repo(self) -> CheckpointRepo:
        return self._build_repo("checkpoint_repo", self._sqlite_checkpoint_repo)

    def run_event_repo(self) -> RunEventRepo:
        return self._build_repo("run_event_repo", self._sqlite_run_event_repo)

    def file_operation_repo(self) -> FileOperationRepo:
        return self._build_repo("file_operation_repo", self._sqlite_file_operation_repo)

    def summary_repo(self) -> SummaryRepo:
        return self._build_repo("summary_repo", self._sqlite_summary_repo)

    def queue_repo(self) -> QueueRepo:
        return self._build_repo("queue_repo", self._sqlite_queue_repo)

    def eval_repo(self) -> EvalRepo:
        return self._build_repo("eval_repo", self._sqlite_eval_repo)

    def sandbox_volume_repo(self) -> SandboxVolumeRepo:
        return self._build_repo("sandbox_volume_repo", self._sqlite_sandbox_volume_repo)

    def provider_event_repo(self) -> ProviderEventRepo:
        return self._build_repo("provider_event_repo", self._sqlite_provider_event_repo)

    def lease_repo(self) -> LeaseRepo:
        return self._build_repo("lease_repo", self._sqlite_lease_repo)

    def terminal_repo(self) -> TerminalRepo:
        return self._build_repo("terminal_repo", self._sqlite_terminal_repo)

    def chat_session_repo(self) -> ChatSessionRepo:
        return self._build_repo("chat_session_repo", self._sqlite_chat_session_repo)

    def purge_thread(self, thread_id: str) -> None:
        """Delete all data for a thread across all repos."""
        checkpoint = self.checkpoint_repo()
        try:
            checkpoint.delete_thread_data(thread_id)
        finally:
            checkpoint.close()

        # threads table is managed via app.state.thread_repo, not StorageContainer

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

    def provider_for(self, repo_name: str) -> StorageStrategy:
        return self._provider_for(repo_name)

    def _provider_for(self, repo_name: str) -> StorageStrategy:
        if repo_name not in self._REPO_NAMES:
            supported = ", ".join(self._REPO_NAMES)
            raise ValueError(f"Unknown repo name: {repo_name}. Supported repo names: {supported}")
        return self._repo_providers[repo_name]

    def _build_repo(self, name: str, sqlite_factory):
        """Generic repo builder: supabase via registry, sqlite via factory."""
        if self._provider_for(name) == "supabase":
            if self._supabase_client is None:
                raise RuntimeError(
                    f"Supabase strategy {name} requires supabase_client. "
                    "Pass supabase_client=... into StorageContainer."
                )
            mod_path, cls_name = _REPO_REGISTRY[name]
            mod = importlib.import_module(mod_path)
            return getattr(mod, cls_name)(client=self._supabase_client)
        return sqlite_factory()

    @classmethod
    def _resolve_repo_providers(
        cls,
        *,
        default_strategy: StorageStrategy,
        repo_providers: RepoProviderMap | None,
        legacy_supabase_bindings: Mapping[str, Any] | None,
    ) -> dict[str, StorageStrategy]:
        if repo_providers is not None and legacy_supabase_bindings is not None:
            raise ValueError("Use either repo_providers or supabase_bindings, not both.")

        overrides: Mapping[str, Any] = repo_providers or legacy_supabase_bindings or {}
        unknown_repos = sorted(set(overrides.keys()) - set(cls._REPO_NAMES))
        if unknown_repos:
            supported = ", ".join(cls._REPO_NAMES)
            unknown = ", ".join(unknown_repos)
            raise ValueError(f"Unknown repo provider bindings: {unknown}. Supported repo names: {supported}")

        resolved: dict[str, StorageStrategy] = {name: default_strategy for name in cls._REPO_NAMES}
        # @@@repo-provider-override - default strategy keeps current behavior; only explicitly listed repos diverge.
        for repo_name, provider in overrides.items():
            if not isinstance(provider, str):
                raise ValueError(
                    f"Invalid provider value for {repo_name}: {provider!r}. Expected 'sqlite' or 'supabase'."
                )
            normalized = provider.strip().lower()
            if normalized not in cls._SUPPORTED_STRATEGIES:
                supported = ", ".join(sorted(cls._SUPPORTED_STRATEGIES))
                raise ValueError(
                    f"Unsupported provider for {repo_name}: {provider!r}. Supported providers: {supported}"
                )
            resolved[repo_name] = normalized
        return resolved

    def _sqlite_checkpoint_repo(self):
        from storage.providers.sqlite.checkpoint_repo import SQLiteCheckpointRepo

        return SQLiteCheckpointRepo(db_path=self._main_db)

    def _sqlite_run_event_repo(self):
        from storage.providers.sqlite.run_event_repo import SQLiteRunEventRepo

        return SQLiteRunEventRepo(db_path=self._run_event_db)

    def _sqlite_file_operation_repo(self):
        from storage.providers.sqlite.file_operation_repo import SQLiteFileOperationRepo

        return SQLiteFileOperationRepo(db_path=self._file_op_db)

    def _sqlite_summary_repo(self):
        from storage.providers.sqlite.summary_repo import SQLiteSummaryRepo

        return SQLiteSummaryRepo(db_path=self._summary_db)

    def _sqlite_queue_repo(self):
        from storage.providers.sqlite.queue_repo import SQLiteQueueRepo

        return SQLiteQueueRepo(db_path=self._queue_db)

    def _sqlite_eval_repo(self):
        from storage.providers.sqlite.eval_repo import SQLiteEvalRepo

        return SQLiteEvalRepo(db_path=self._eval_db)

    def _sqlite_sandbox_volume_repo(self):
        from storage.providers.sqlite.sandbox_volume_repo import SQLiteSandboxVolumeRepo

        return SQLiteSandboxVolumeRepo()

    def _sqlite_provider_event_repo(self):
        from storage.providers.sqlite.provider_event_repo import SQLiteProviderEventRepo

        return SQLiteProviderEventRepo(db_path=self._sandbox_db)

    def _sqlite_lease_repo(self):
        from storage.providers.sqlite.lease_repo import SQLiteLeaseRepo

        return SQLiteLeaseRepo(db_path=self._sandbox_db)

    def _sqlite_terminal_repo(self):
        from storage.providers.sqlite.terminal_repo import SQLiteTerminalRepo

        return SQLiteTerminalRepo(db_path=self._sandbox_db)

    def _sqlite_chat_session_repo(self):
        from storage.providers.sqlite.chat_session_repo import SQLiteChatSessionRepo

        return SQLiteChatSessionRepo(db_path=self._sandbox_db)
