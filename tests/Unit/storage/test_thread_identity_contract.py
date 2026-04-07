import pytest
from pydantic import ValidationError

from storage.contracts import ThreadRow


def test_thread_row_rejects_blank_id() -> None:
    with pytest.raises(ValidationError, match="thread.id must not be blank"):
        ThreadRow(
            id=" ",
            agent_user_id="agent-user-1",
            sandbox_type="local",
            created_at=1.0,
        )


def test_thread_row_rejects_blank_agent_user_id() -> None:
    with pytest.raises(ValidationError, match="thread.agent_user_id must not be blank"):
        ThreadRow(
            id="thread-1",
            agent_user_id=" ",
            sandbox_type="local",
            created_at=1.0,
        )


def test_thread_row_rejects_blank_sandbox_type() -> None:
    with pytest.raises(ValidationError, match="thread.sandbox_type must not be blank"):
        ThreadRow(
            id="thread-1",
            agent_user_id="agent-user-1",
            sandbox_type=" ",
            created_at=1.0,
        )


def test_thread_row_defaults_status_to_active() -> None:
    row = ThreadRow(
        id="thread-1",
        agent_user_id="agent-user-1",
        sandbox_type="local",
        created_at=1.0,
    )

    assert row.status == "active"


def test_thread_row_accepts_runtime_fields() -> None:
    row = ThreadRow(
        id="thread-1",
        agent_user_id="agent-user-1",
        sandbox_type="daytona",
        model="gpt-5.4",
        cwd="/workspace/demo",
        status="idle",
        created_at=1.0,
        updated_at=2.0,
        last_active_at=3.0,
    )

    assert row.model == "gpt-5.4"
    assert row.cwd == "/workspace/demo"
    assert row.status == "idle"
    assert row.last_active_at == 3.0
