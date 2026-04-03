from backend.web.models.requests import CreateThreadRequest


def test_create_thread_request_accepts_legacy_sandbox_type_key() -> None:
    payload = CreateThreadRequest.model_validate(
        {
            "member_id": "member-1",
            "sandbox_type": "daytona_selfhost",
            "model": "gpt-5.4-mini",
        }
    )

    assert payload.sandbox == "daytona_selfhost"


def test_create_thread_request_prefers_primary_sandbox_key() -> None:
    payload = CreateThreadRequest.model_validate(
        {
            "member_id": "member-1",
            "sandbox": "local",
            "sandbox_type": "daytona_selfhost",
        }
    )

    assert payload.sandbox == "local"
