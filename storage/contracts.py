"""Structural storage contracts for repo-level provider parity."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field, field_validator, model_validator

NotificationType = Literal["steer", "command", "agent", "chat"]


# ---------------------------------------------------------------------------
# Sandbox — repo protocols
# ---------------------------------------------------------------------------


class LeaseRepo(Protocol):
    """Sandbox lease CRUD. Returns raw dicts — domain object construction is the consumer's job."""

    def close(self) -> None: ...
    def get(self, lease_id: str) -> dict[str, Any] | None: ...
    def create(self, lease_id: str, provider_name: str, volume_id: str | None = None) -> dict[str, Any]: ...
    def find_by_instance(self, *, provider_name: str, instance_id: str) -> dict[str, Any] | None: ...
    def adopt_instance(self, *, lease_id: str, provider_name: str, instance_id: str, status: str = "unknown") -> dict[str, Any]: ...
    def observe_status(self, *, lease_id: str, status: str, observed_at: Any = None) -> dict[str, Any]: ...
    def persist_metadata(
        self,
        *,
        lease_id: str,
        recipe_id: str | None,
        recipe_json: str | None,
        desired_state: str,
        observed_state: str,
        version: int,
        observed_at: Any,
        last_error: str | None,
        needs_refresh: bool,
        refresh_hint_at: Any = None,
        status: str,
    ) -> dict[str, Any]: ...
    def mark_needs_refresh(self, lease_id: str, hint_at: Any = None) -> bool: ...
    def set_volume_id(self, lease_id: str, volume_id: str) -> bool: ...
    def delete(self, lease_id: str) -> None: ...
    def list_all(self) -> list[dict[str, Any]]: ...
    def list_by_provider(self, provider_name: str) -> list[dict[str, Any]]: ...


class TerminalRepo(Protocol):
    """Abstract terminal CRUD + thread pointer management."""

    def close(self) -> None: ...
    def summarize_threads(self, thread_ids: list[str]) -> dict[str, dict[str, str | None]]: ...
    def get_active(self, thread_id: str) -> dict[str, Any] | None: ...
    def get_default(self, thread_id: str) -> dict[str, Any] | None: ...
    def get_by_id(self, terminal_id: str) -> dict[str, Any] | None: ...
    def get_latest_by_lease(self, lease_id: str) -> dict[str, Any] | None: ...
    def get_timestamps(self, terminal_id: str) -> tuple[str | None, str | None]: ...
    def list_by_thread(self, thread_id: str) -> list[dict[str, Any]]: ...
    def create(self, terminal_id: str, thread_id: str, lease_id: str, initial_cwd: str = "/root") -> dict[str, Any]: ...
    def persist_state(self, *, terminal_id: str, cwd: str, env_delta_json: str, state_version: int) -> None: ...
    def set_active(self, thread_id: str, terminal_id: str) -> None: ...
    def delete_by_thread(self, thread_id: str) -> None: ...
    def delete(self, terminal_id: str) -> None: ...
    def list_all(self) -> list[dict[str, Any]]: ...


class ProviderEventRepo(Protocol):
    """Webhook event persistence."""

    def close(self) -> None: ...
    def record(
        self,
        *,
        provider_name: str,
        instance_id: str,
        event_type: str,
        payload: dict[str, Any],
        matched_lease_id: str | None,
    ) -> None: ...
    def list_recent(self, limit: int = 100) -> list[dict[str, Any]]: ...


class ChatSessionRepo(Protocol):
    """Chat session + terminal command persistence."""

    def close(self) -> None: ...
    def create_session(
        self,
        session_id: str,
        thread_id: str,
        terminal_id: str,
        lease_id: str,
        *,
        runtime_id: str | None = None,
        status: str = "active",
        idle_ttl_sec: int = 600,
        max_duration_sec: int = 86400,
        budget_json: str | None = None,
        started_at: str | None = None,
        last_active_at: str | None = None,
    ) -> dict[str, Any]: ...
    def get_session(self, thread_id: str, terminal_id: str | None = None) -> dict[str, Any] | None: ...
    def get_session_by_id(self, session_id: str) -> dict[str, Any] | None: ...
    def get_session_policy(self, session_id: str) -> dict[str, Any] | None: ...
    def load_status(self, session_id: str) -> str | None: ...
    def touch(self, session_id: str, last_active_at: str | None = None, status: str | None = None) -> None: ...
    def touch_thread_activity(self, thread_id: str, last_active_at: str | None = None) -> None: ...
    def pause(self, session_id: str) -> None: ...
    def resume(self, session_id: str) -> None: ...
    def upsert_command(
        self,
        *,
        command_id: str,
        terminal_id: str,
        chat_session_id: str | None,
        command_line: str,
        cwd: str,
        status: str,
        stdout: str,
        stderr: str,
        exit_code: int | None,
        updated_at: str,
        finished_at: str | None,
        created_at: str | None = None,
    ) -> None: ...
    def append_command_chunks(
        self,
        *,
        command_id: str,
        stdout_chunks: list[str],
        stderr_chunks: list[str],
        created_at: str,
    ) -> None: ...
    def get_command(self, *, command_id: str, terminal_id: str) -> dict[str, Any] | None: ...
    def list_command_chunks(self, *, command_id: str) -> list[dict[str, Any]]: ...
    def find_command_terminal_id(self, *, command_id: str, thread_id: str) -> str | None: ...
    def delete_session(self, session_id: str, *, reason: str = "closed") -> None: ...
    def delete_by_thread(self, thread_id: str) -> None: ...
    def terminal_has_running_command(self, terminal_id: str) -> bool: ...
    def lease_has_running_command(self, lease_id: str) -> bool: ...
    def list_active(self) -> list[dict[str, Any]]: ...
    def list_all(self) -> list[dict[str, Any]]: ...
    def cleanup_expired(self) -> list[str]: ...


class SandboxMonitorRepo(Protocol):
    """Read-only monitor queries over sandbox/session/lease state."""

    def close(self) -> None: ...
    def query_threads(self, *, thread_id: str | None = None) -> list[dict[str, Any]]: ...
    def query_thread_summary(self, thread_id: str) -> dict[str, Any] | None: ...
    def query_thread_sessions(self, thread_id: str) -> list[dict[str, Any]]: ...
    def query_leases(self) -> list[dict[str, Any]]: ...
    def list_leases_with_threads(self) -> list[dict[str, Any]]: ...
    def query_lease(self, lease_id: str) -> dict[str, Any] | None: ...
    def query_lease_sessions(self, lease_id: str) -> list[dict[str, Any]]: ...
    def query_lease_threads(self, lease_id: str) -> list[dict[str, Any]]: ...
    def query_lease_events(self, lease_id: str) -> list[dict[str, Any]]: ...
    def list_sessions_with_leases(self) -> list[dict[str, Any]]: ...
    def list_probe_targets(self) -> list[dict[str, Any]]: ...
    def query_lease_instance_id(self, lease_id: str) -> str | None: ...
    def query_lease_instance_ids(self, lease_ids: list[str]) -> dict[str, str | None]: ...


# ---------------------------------------------------------------------------
# User / Agent / Chat — enums + row types
# ---------------------------------------------------------------------------


class UserType(StrEnum):
    HUMAN = "human"
    AGENT = "agent"


class UserRow(BaseModel):
    id: str
    type: UserType
    display_name: str
    owner_user_id: str | None = None
    agent_config_id: str | None = None
    next_thread_seq: int = 0
    avatar: str | None = None
    email: str | None = None
    mycel_id: int | None = None
    created_at: float
    updated_at: float | None = None

    @model_validator(mode="after")
    def _validate_identity_shape(self) -> UserRow:
        # @@@user-row-shape - users are the unified social identity surface, so
        # human/agent optional fields must fail loudly instead of drifting into
        # mixed half-valid rows.
        if self.type is UserType.HUMAN:
            if self.owner_user_id is not None:
                raise ValueError("human users must not carry owner_user_id")
            if self.agent_config_id is not None:
                raise ValueError("human users must not carry agent_config_id")
            return self
        if self.owner_user_id is None:
            raise ValueError("agent users require owner_user_id")
        if self.agent_config_id is None:
            raise ValueError("agent users require agent_config_id")
        return self


class AgentConfigRow(BaseModel):
    id: str
    agent_user_id: str
    name: str
    description: str = ""
    model: str | None = None
    tools: list[str] = Field(default_factory=list)
    system_prompt: str = ""
    status: str = "draft"
    version: str = "0.1.0"
    runtime: dict[str, Any] = Field(default_factory=dict)
    mcp: dict[str, Any] = Field(default_factory=dict)
    created_at: int
    updated_at: int | None = None

    @field_validator("id", "agent_user_id", "name")
    @classmethod
    def _validate_non_blank(cls, value: str, info: Any) -> str:
        if not value.strip():
            raise ValueError(f"agent_config.{info.field_name} must not be blank")
        return value


class AgentRuleRow(BaseModel):
    id: str
    agent_config_id: str
    filename: str
    content: str

    @field_validator("id", "agent_config_id")
    @classmethod
    def _validate_identity_fields(cls, value: str, info: Any) -> str:
        if not value.strip():
            raise ValueError(f"agent_rule.{info.field_name} must not be blank")
        return value


class AgentSkillRow(BaseModel):
    id: str
    agent_config_id: str
    name: str
    content: str
    meta: dict[str, Any] = Field(default_factory=dict)

    @field_validator("id", "agent_config_id")
    @classmethod
    def _validate_identity_fields(cls, value: str, info: Any) -> str:
        if not value.strip():
            raise ValueError(f"agent_skill.{info.field_name} must not be blank")
        return value


class AgentSubAgentRow(BaseModel):
    id: str
    agent_config_id: str
    name: str
    description: str | None = None
    model: str | None = None
    tools: list[Any] = Field(default_factory=list)
    system_prompt: str | None = None

    @field_validator("id", "agent_config_id")
    @classmethod
    def _validate_identity_fields(cls, value: str, info: Any) -> str:
        if not value.strip():
            raise ValueError(f"agent_sub_agent.{info.field_name} must not be blank")
        return value


class ThreadRow(BaseModel):
    id: str
    agent_user_id: str
    owner_user_id: str | None = None
    current_workspace_id: str | None = None
    sandbox_type: str
    model: str | None = None
    cwd: str | None = None
    status: str = "active"
    is_main: bool = False
    branch_index: int = 0
    created_at: float
    updated_at: float | None = None
    last_active_at: float | None = None

    @field_validator("id", "agent_user_id", "sandbox_type")
    @classmethod
    def _validate_non_blank(cls, value: str, info: Any) -> str:
        if not value.strip():
            raise ValueError(f"thread.{info.field_name} must not be blank")
        return value


class WorkspaceRow(BaseModel):
    id: str
    sandbox_id: str
    owner_user_id: str
    workspace_path: str
    name: str | None = None
    created_at: float | str
    updated_at: float | str | None = None

    @field_validator("id", "sandbox_id", "owner_user_id", "workspace_path")
    @classmethod
    def _validate_non_blank(cls, value: str, info: Any) -> str:
        if not value.strip():
            raise ValueError(f"workspace.{info.field_name} must not be blank")
        return value


class ChatRow(BaseModel):
    id: str
    type: str
    created_by_user_id: str
    title: str | None = None
    status: str = "active"
    next_message_seq: int = 0
    created_at: float
    updated_at: float | None = None

    @field_validator("id", "type", "created_by_user_id")
    @classmethod
    def _validate_chat_identity_fields(cls, value: str, info: Any) -> str:
        if not value.strip():
            raise ValueError(f"chat.{info.field_name} must not be blank")
        return value


class ChatMemberRow(BaseModel):
    chat_id: str
    user_id: str
    role: str = "member"
    joined_at: float
    last_read_seq: int = 0
    muted: bool = False
    mute_until: float | None = None
    version: int = 0

    @field_validator("chat_id", "user_id")
    @classmethod
    def _validate_chat_member_identity_fields(cls, value: str, info: Any) -> str:
        if not value.strip():
            raise ValueError(f"chat_member.{info.field_name} must not be blank")
        return value

    @field_validator("last_read_seq")
    @classmethod
    def _validate_last_read_seq(cls, value: int) -> int:
        if value < 0:
            raise ValueError("chat_member.last_read_seq must be >= 0")
        return value


class MessageRow(BaseModel):
    id: str
    chat_id: str
    seq: int
    sender_user_id: str
    content: str
    content_type: str = "text/plain"
    message_type: str = "text"
    signal: str | None = None
    mentions: list[str] = Field(default_factory=list)
    reply_to_message_id: str | None = None
    ai_metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: float
    delivered_at: float | None = None
    edited_at: float | None = None
    retracted_at: float | None = None
    deleted_at: float | None = None

    @field_validator("id", "chat_id", "sender_user_id")
    @classmethod
    def _validate_message_identity_fields(cls, value: str, info: Any) -> str:
        if not value.strip():
            raise ValueError(f"message.{info.field_name} must not be blank")
        return value

    @field_validator("seq")
    @classmethod
    def _validate_message_seq(cls, value: int) -> int:
        if value < 1:
            raise ValueError("message.seq must be >= 1")
        return value


class ContactEdgeRow(BaseModel):
    source_user_id: str
    target_user_id: str
    kind: str = "normal"
    state: str = "active"
    alias: str | None = None
    note: str | None = None
    pinned: bool = False
    muted: bool = False
    archived: bool = False
    blocked: bool = False
    snapshot: dict[str, Any] = Field(default_factory=dict)
    version: int = 0
    created_at: float
    updated_at: float | None = None

    @field_validator("source_user_id", "target_user_id", "kind", "state")
    @classmethod
    def _validate_contact_identity_fields(cls, value: str, info: Any) -> str:
        if not value.strip():
            raise ValueError(f"contact.{info.field_name} must not be blank")
        return value


class RelationshipRow(BaseModel):
    user_low: str
    user_high: str
    kind: str
    state: str = "pending"
    initiator_user_id: str
    version: int = 0
    created_at: float
    updated_at: float | None = None

    @field_validator("user_low", "user_high", "kind", "initiator_user_id")
    @classmethod
    def _validate_relationship_identity_fields(cls, value: str, info: Any) -> str:
        if not value.strip():
            raise ValueError(f"relationship.{info.field_name} must not be blank")
        return value

    @model_validator(mode="after")
    def _validate_sorted_pair(self) -> RelationshipRow:
        # @@@relationship-sorted-pair - symmetric edges must collapse to one
        # canonical row, so the storage contract rejects unsorted user pairs.
        if self.user_low >= self.user_high:
            raise ValueError("relationship.user_low must be < relationship.user_high")
        return self


# ---------------------------------------------------------------------------
# Delivery strategy — contact relationships + delivery actions
# ---------------------------------------------------------------------------


class DeliveryAction(StrEnum):
    """What to do when a chat message reaches a recipient."""

    DELIVER = "deliver"  # full delivery: inject into agent context, wake agent
    NOTIFY = "notify"  # red dot only: message stored, unread counted, no delivery
    DROP = "drop"  # silent: message stored but invisible to this user


ContactRelation = Literal["normal", "blocked", "muted"]


class ContactRow(BaseModel):
    """Directional relationship between two social identities. A→B independent of B→A."""

    owner_id: str  # social identity: direct user_id for humans, thread-attached user_id for agents
    target_id: str  # social identity: direct user_id for humans, thread-attached user_id for agents
    relation: ContactRelation
    created_at: float
    updated_at: float | None = None


class CheckpointRepo(Protocol):
    def close(self) -> None: ...
    def list_thread_ids(self) -> list[str]: ...
    def delete_thread_data(self, thread_id: str) -> None: ...
    def delete_checkpoints_by_ids(self, thread_id: str, checkpoint_ids: list[str]) -> None: ...


@runtime_checkable
class RunEventRepo(Protocol):
    def close(self) -> None: ...
    def append_event(
        self,
        thread_id: str,
        run_id: str,
        event_type: str,
        data: dict[str, Any],
        message_id: str | None = None,
    ) -> int: ...
    def list_events(
        self,
        thread_id: str,
        run_id: str,
        *,
        after: int = 0,
        limit: int = 200,
    ) -> list[dict[str, Any]]: ...
    def latest_seq(self, thread_id: str) -> int: ...
    def latest_run_id(self, thread_id: str) -> str | None: ...
    def list_run_ids(self, thread_id: str) -> list[str]: ...
    def run_start_seq(self, thread_id: str, run_id: str) -> int: ...
    def delete_runs(self, thread_id: str, run_ids: list[str]) -> int: ...
    def delete_thread_events(self, thread_id: str) -> int: ...


class RecipeRepo(Protocol):
    def close(self) -> None: ...
    def list_by_owner(self, owner_user_id: str) -> list[dict[str, Any]]: ...
    def get(self, owner_user_id: str, recipe_id: str) -> dict[str, Any] | None: ...
    def upsert(
        self,
        *,
        owner_user_id: str,
        recipe_id: str,
        kind: str,
        provider_type: str,
        data: dict[str, Any],
        created_at: int | None = None,
    ) -> dict[str, Any]: ...
    def delete(self, owner_user_id: str, recipe_id: str) -> bool: ...


class ThreadLaunchPrefRepo(Protocol):
    def close(self) -> None: ...
    def get(self, owner_user_id: str, agent_user_id: str) -> dict[str, Any] | None: ...
    def save_confirmed(self, owner_user_id: str, agent_user_id: str, config: dict[str, Any]) -> None: ...
    def save_successful(self, owner_user_id: str, agent_user_id: str, config: dict[str, Any]) -> None: ...
    def delete_by_agent_user_id(self, agent_user_id: str) -> int: ...


class UserSettingsRepo(Protocol):
    def close(self) -> None: ...
    def get(self, user_id: str) -> dict[str, Any]: ...
    def set_default_workspace(self, user_id: str, workspace: str) -> None: ...
    def add_recent_workspace(self, user_id: str, workspace: str) -> None: ...
    def set_default_model(self, user_id: str, model: str) -> None: ...
    def get_models_config(self, user_id: str) -> dict[str, Any] | None: ...
    def set_models_config(self, user_id: str, config: dict[str, Any]) -> None: ...
    def get_account_resource_limits(self, user_id: str) -> dict[str, Any] | None: ...


class AgentConfigRepo(Protocol):
    def close(self) -> None: ...
    def get_config(self, agent_config_id: str) -> dict[str, Any] | None: ...
    def save_config(self, agent_config_id: str, data: dict[str, Any]) -> None: ...
    def delete_config(self, agent_config_id: str) -> None: ...
    def list_rules(self, agent_config_id: str) -> list[dict[str, Any]]: ...
    def save_rule(self, agent_config_id: str, filename: str, content: str, rule_id: str | None = None) -> dict[str, Any]: ...
    def delete_rule(self, rule_id: str) -> None: ...
    def list_skills(self, agent_config_id: str) -> list[dict[str, Any]]: ...
    def save_skill(
        self,
        agent_config_id: str,
        name: str,
        content: str,
        meta: dict[str, Any] | None = None,
        skill_id: str | None = None,
    ) -> dict[str, Any]: ...
    def delete_skill(self, skill_id: str) -> None: ...
    def list_sub_agents(self, agent_config_id: str) -> list[dict[str, Any]]: ...
    def save_sub_agent(
        self,
        agent_config_id: str,
        name: str,
        *,
        description: str | None = None,
        model: str | None = None,
        tools: list[Any] | None = None,
        system_prompt: str | None = None,
        sub_agent_id: str | None = None,
    ) -> dict[str, Any]: ...
    def delete_sub_agent(self, sub_agent_id: str) -> None: ...


class AgentRegistryRepo(Protocol):
    def close(self) -> None: ...
    def register(
        self,
        *,
        agent_id: str,
        name: str,
        thread_id: str,
        status: str,
        parent_agent_id: str | None,
        subagent_type: str | None,
    ) -> None: ...
    def get_by_id(self, agent_id: str) -> tuple[Any, ...] | None: ...
    def list_running_by_name(self, name: str) -> list[tuple[Any, ...]]: ...
    def update_status(self, agent_id: str, status: str) -> None: ...
    def get_latest_by_name_and_parent(self, name: str, parent_agent_id: str | None) -> tuple[Any, ...] | None: ...
    def list_running(self) -> list[tuple[Any, ...]]: ...


class ToolTaskRepo(Protocol):
    def close(self) -> None: ...
    def next_id(self, thread_id: str) -> str: ...
    def get(self, thread_id: str, task_id: str) -> Any | None: ...
    def list_all(self, thread_id: str) -> list[Any]: ...
    def insert(self, thread_id: str, task: Any) -> None: ...
    def update(self, thread_id: str, task: Any) -> None: ...
    def delete(self, thread_id: str, task_id: str) -> None: ...


class SyncFileRepo(Protocol):
    def close(self) -> None: ...
    def track_file(self, thread_id: str, relative_path: str, checksum: str, timestamp: int) -> None: ...
    def track_files_batch(self, thread_id: str, file_records: list[tuple[str, str, int]]) -> None: ...
    def get_file_info(self, thread_id: str, relative_path: str) -> dict[str, Any] | None: ...
    def get_all_files(self, thread_id: str) -> dict[str, str]: ...
    def clear_thread(self, thread_id: str) -> int: ...


class ResourceSnapshotRepo(Protocol):
    def close(self) -> None: ...
    def upsert_lease_resource_snapshot(
        self,
        *,
        lease_id: str,
        provider_name: str,
        observed_state: str,
        probe_mode: str,
        cpu_used: float | None = None,
        cpu_limit: float | None = None,
        memory_used_mb: float | None = None,
        memory_total_mb: float | None = None,
        disk_used_gb: float | None = None,
        disk_total_gb: float | None = None,
        network_rx_kbps: float | None = None,
        network_tx_kbps: float | None = None,
        probe_error: str | None = None,
    ) -> None: ...
    def list_snapshots_by_lease_ids(self, lease_ids: list[str]) -> dict[str, dict[str, Any]]: ...


class FileOperationRepo(Protocol):
    def close(self) -> None: ...
    def record(
        self,
        thread_id: str,
        checkpoint_id: str,
        operation_type: str,
        file_path: str,
        before_content: str | None,
        after_content: str,
        changes: list[dict] | None = None,
    ) -> str: ...
    def delete_thread_operations(self, thread_id: str) -> int: ...


# @@@summary-row-contract - standardize summary row payload as dict to keep provider parity explicit for static type checks.
type SummaryRow = dict[str, Any]


class SummaryRepo(Protocol):
    def ensure_tables(self) -> None: ...
    def save_summary(
        self,
        summary_id: str,
        thread_id: str,
        summary_text: str,
        compact_up_to_index: int,
        compacted_at: int,
        is_split_turn: bool,
        split_turn_prefix: str | None,
        created_at: str,
    ) -> None: ...
    def get_latest_summary_row(self, thread_id: str) -> SummaryRow | None: ...
    def list_summaries(self, thread_id: str) -> list[dict[str, object]]: ...
    def delete_thread_summaries(self, thread_id: str) -> None: ...
    def close(self) -> None: ...


class QueueItem(BaseModel):
    """A dequeued message with its notification type."""

    content: str
    notification_type: NotificationType
    source: str | None = None  # "owner" | "external" | "system"
    sender_id: str | None = None  # social identity slot; full agent-handle split still pending
    sender_name: str | None = None
    sender_avatar_url: str | None = None
    is_steer: bool = False


class QueueRepo(Protocol):
    def close(self) -> None: ...
    def enqueue(
        self,
        thread_id: str,
        content: str,
        notification_type: NotificationType = "steer",
        source: str | None = None,
        sender_id: str | None = None,
        sender_name: str | None = None,
    ) -> None: ...
    def dequeue(self, thread_id: str) -> QueueItem | None: ...
    def drain_all(self, thread_id: str) -> list[QueueItem]: ...
    def peek(self, thread_id: str) -> bool: ...
    def list_queue(self, thread_id: str) -> list[dict[str, Any]]: ...
    def clear_queue(self, thread_id: str) -> None: ...
    def count(self, thread_id: str) -> int: ...


class SandboxVolumeRepo(Protocol):
    """Sandbox volume metadata. Stores serialized VolumeSource per lease."""

    def close(self) -> None: ...
    def create(self, volume_id: str, source_json: str, name: str | None, created_at: str) -> None: ...
    def get(self, volume_id: str) -> dict[str, Any] | None: ...
    def update_source(self, volume_id: str, source_json: str) -> None: ...
    def list_all(self) -> list[dict[str, Any]]: ...
    def delete(self, volume_id: str) -> bool: ...


class EvalRepo(Protocol):
    def upsert_run_header(
        self,
        *,
        run_id: str,
        thread_id: str,
        started_at: str,
        user_message: str,
        status: str,
    ) -> None: ...
    def finalize_run(
        self,
        *,
        run_id: str,
        finished_at: str,
        final_response: str,
        status: str,
        run_tree_json: str,
        trajectory_json: str,
    ) -> None: ...
    def save_trajectory(self, trajectory: Any, trajectory_json: str) -> str: ...
    def save_metrics(self, run_id: str, tier: str, timestamp: str, metrics_json: str) -> None: ...
    def get_trajectory_json(self, run_id: str) -> str | None: ...
    def get_run(self, run_id: str) -> dict | None: ...
    def list_runs(self, thread_id: str | None = None, limit: int = 50) -> list[dict]: ...
    def get_metrics(self, run_id: str, tier: str | None = None) -> list[dict]: ...


class EvaluationBatchRepo(Protocol):
    def create_batch(self, batch: dict[str, Any]) -> dict[str, Any]: ...
    def get_batch(self, batch_id: str) -> dict[str, Any] | None: ...
    def list_batches(self, limit: int = 50) -> list[dict[str, Any]]: ...
    def update_batch(
        self,
        batch_id: str,
        *,
        status: str | None = None,
        updated_at: str | None = None,
        summary_json: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None: ...
    def create_batch_run(self, batch_run: dict[str, Any]) -> dict[str, Any]: ...
    def list_batch_runs(self, batch_id: str) -> list[dict[str, Any]]: ...
    def get_batch_run_by_eval_run_id(self, eval_run_id: str) -> dict[str, Any] | None: ...
    def list_batch_runs_by_thread_id(self, thread_id: str) -> list[dict[str, Any]]: ...
    def update_batch_run(
        self,
        batch_run_id: str,
        *,
        status: str | None = None,
        thread_id: str | None = None,
        eval_run_id: str | None = None,
        started_at: str | None = None,
        finished_at: str | None = None,
        summary_json: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None: ...


class UserRepo(Protocol):
    def close(self) -> None: ...
    def create(self, row: UserRow) -> None: ...
    def get_by_id(self, user_id: str) -> UserRow | None: ...
    def get_by_email(self, email: str) -> UserRow | None: ...
    def get_by_mycel_id(self, mycel_id: int) -> UserRow | None: ...
    def list_by_ids(self, user_ids: list[str]) -> list[UserRow]: ...
    def list_all(self) -> list[UserRow]: ...
    def list_by_type(self, user_type: str) -> list[UserRow]: ...
    def list_by_owner_user_id(self, owner_user_id: str) -> list[UserRow]: ...
    def update(self, user_id: str, **fields: Any) -> None: ...
    def increment_thread_seq(self, user_id: str) -> int: ...
    def delete(self, user_id: str) -> None: ...


class ChatRepo(Protocol):
    def close(self) -> None: ...
    def create(self, row: ChatRow) -> None: ...
    def get_by_id(self, chat_id: str) -> ChatRow | None: ...
    def list_by_ids(self, chat_ids: list[str]) -> list[ChatRow]: ...
    def delete(self, chat_id: str) -> None: ...


class WorkspaceRepo(Protocol):
    def close(self) -> None: ...
    def create(self, row: WorkspaceRow) -> None: ...
    def get_by_id(self, workspace_id: str) -> WorkspaceRow | None: ...
    def list_by_sandbox_id(self, sandbox_id: str) -> list[WorkspaceRow]: ...


class ThreadRepo(Protocol):
    def close(self) -> None: ...
    def create(
        self,
        thread_id: str,
        agent_user_id: str,
        sandbox_type: str,
        cwd: str | None = None,
        created_at: float = 0,
        *,
        model: str | None = None,
        is_main: bool,
        branch_index: int,
        owner_user_id: str,
        status: str = "active",
        updated_at: float | None = None,
        last_active_at: float | None = None,
        current_workspace_id: str,
    ) -> None: ...
    def list_by_ids(self, thread_ids: list[str]) -> list[dict[str, Any]]: ...
    def get_by_id(self, thread_id: str) -> dict[str, Any] | None: ...
    def get_by_user_id(self, user_id: str) -> dict[str, Any] | None: ...
    def get_default_thread(self, agent_user_id: str) -> dict[str, Any] | None: ...
    def list_default_threads(self, agent_user_ids: list[str]) -> dict[str, dict[str, Any]]: ...
    def get_next_branch_index(self, agent_user_id: str) -> int: ...
    def list_by_agent_user(self, agent_user_id: str) -> list[dict[str, Any]]: ...
    def list_by_owner_user_id(self, owner_user_id: str) -> list[dict[str, Any]]: ...
    def update(self, thread_id: str, *, model: str) -> None: ...
    def delete(self, thread_id: str) -> None: ...


class ContactRepo(Protocol):
    def close(self) -> None: ...
    def upsert(self, row: ContactEdgeRow) -> None: ...
    def get(self, owner_id: str, target_id: str) -> ContactEdgeRow | None: ...
    def list_for_user(self, owner_id: str) -> list[ContactEdgeRow]: ...
    def delete(self, owner_id: str, target_id: str) -> None: ...
    def delete_for_user(self, user_id: str) -> None: ...


class DeliveryResolver(Protocol):
    """Evaluates delivery strategy for a chat message recipient.

    Checks contact-level block/mute, then chat-level mute, then defaults to DELIVER.
    """

    def resolve(self, recipient_id: str, chat_id: str, sender_id: str, *, is_mentioned: bool = False) -> DeliveryAction: ...


class InviteCodeRepo(Protocol):
    def close(self) -> None: ...
    def generate(self, *, created_by: str | None = None, expires_days: int | None = 7) -> dict: ...
    def get(self, code: str) -> dict | None: ...
    def list_all(self) -> list[dict]: ...
    def use(self, code: str, user_id: str) -> dict | None: ...
    def is_valid(self, code: str) -> bool: ...
    def revoke(self, code: str) -> bool: ...
