from __future__ import annotations


class StorageConflictError(RuntimeError):
    pass


class StaleChatWorkflowVersionError(StorageConflictError):
    def __init__(
        self,
        *,
        chat_id: str,
        expected_state_version: int,
        actual_state_version: int | None,
    ) -> None:
        self.chat_id = chat_id
        self.expected_state_version = expected_state_version
        self.actual_state_version = actual_state_version
        super().__init__(
            f"stale chat workflow state version: chat_id={chat_id!r} expected={expected_state_version!r} actual={actual_state_version!r}"
        )


class StaleChatWorkflowEventVersionError(StorageConflictError):
    def __init__(
        self,
        *,
        chat_id: str,
        event_id: str,
        expected_state_version: int,
        actual_state_version: int | None,
    ) -> None:
        self.chat_id = chat_id
        self.event_id = event_id
        self.expected_state_version = expected_state_version
        self.actual_state_version = actual_state_version
        super().__init__(
            f"stale chat workflow event state version: chat_id={chat_id!r} event_id={event_id!r} "
            f"expected={expected_state_version!r} actual={actual_state_version!r}"
        )
