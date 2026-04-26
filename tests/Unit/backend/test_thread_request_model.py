from backend.web.models.requests import CreateThreadRequest, SendMessageRequest


def test_create_thread_request_accepts_current_agent_user_id() -> None:
    payload = CreateThreadRequest.model_validate({"agent_user_id": "agent-1", "model": "gpt-5.4-mini"})

    assert payload.agent_user_id == "agent-1"


def test_send_message_request_defaults_enable_trajectory_to_false() -> None:
    payload = SendMessageRequest.model_validate({"message": "hello"})

    assert payload.enable_trajectory is False


def test_send_message_request_accepts_enable_trajectory_flag() -> None:
    payload = SendMessageRequest.model_validate({"message": "hello", "enable_trajectory": True})

    assert payload.enable_trajectory is True
