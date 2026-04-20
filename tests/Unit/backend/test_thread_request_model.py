import pytest

from backend.web.models.requests import CreateThreadRequest, SendMessageRequest


def test_create_thread_request_rejects_removed_sandbox_type_key() -> None:
    with pytest.raises(Exception):
        CreateThreadRequest.model_validate(
            {
                "agent_user_id": "agent-1",
                "sandbox_type": "daytona_selfhost",
                "model": "gpt-5.4-mini",
            }
        )


def test_create_thread_request_rejects_removed_member_id_field() -> None:
    with pytest.raises(Exception):
        CreateThreadRequest.model_validate(
            {
                "member_id": "member-1",
                "sandbox": "local",
            }
        )


def test_send_message_request_defaults_enable_trajectory_to_false() -> None:
    payload = SendMessageRequest.model_validate({"message": "hello"})

    assert payload.enable_trajectory is False


def test_send_message_request_accepts_enable_trajectory_flag() -> None:
    payload = SendMessageRequest.model_validate({"message": "hello", "enable_trajectory": True})

    assert payload.enable_trajectory is True
