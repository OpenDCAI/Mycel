import pytest

from storage.contracts import SandboxRow


def test_sandbox_row_accepts_thin_container_shape() -> None:
    row = SandboxRow(
        id="sandbox-1",
        owner_user_id="owner-1",
        provider_name="daytona_selfhost",
        provider_env_id="env-1",
        sandbox_template_id="tpl-1",
        desired_state="running",
        observed_state="running",
        status="ready",
        observed_at=123.0,
        last_error=None,
        config={"region": "cn"},
        created_at=100.0,
        updated_at=123.0,
    )

    assert row.id == "sandbox-1"
    assert row.config == {"region": "cn"}


def test_sandbox_row_rejects_blank_required_identity() -> None:
    with pytest.raises(ValueError, match="sandbox row requires id"):
        SandboxRow(
            id=" ",
            owner_user_id="owner-1",
            provider_name="local",
            provider_env_id=None,
            sandbox_template_id=None,
            desired_state="running",
            observed_state="running",
            status="ready",
            observed_at=1.0,
            last_error=None,
            config={},
            created_at=1.0,
            updated_at=1.0,
        )


def test_sandbox_row_requires_object_config() -> None:
    with pytest.raises(ValueError, match="sandbox row config must be an object"):
        SandboxRow(
            id="sandbox-1",
            owner_user_id="owner-1",
            provider_name="local",
            provider_env_id=None,
            sandbox_template_id=None,
            desired_state="running",
            observed_state="running",
            status="ready",
            observed_at=1.0,
            last_error=None,
            config="bad",
            created_at=1.0,
            updated_at=1.0,
        )
