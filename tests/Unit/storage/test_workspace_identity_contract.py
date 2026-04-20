import pytest

from storage.contracts import WorkspaceRow


def test_workspace_row_accepts_thin_directory_shape() -> None:
    row = WorkspaceRow(
        id="workspace-1",
        sandbox_id="sandbox-1",
        owner_user_id="owner-1",
        workspace_path="/workspace/demo",
        name="demo",
        created_at=1.0,
        updated_at=2.0,
    )

    assert row.workspace_path == "/workspace/demo"


def test_workspace_row_requires_non_blank_identity_fields() -> None:
    with pytest.raises(ValueError, match="workspace.id must not be blank"):
        WorkspaceRow(
            id="   ",
            sandbox_id="sandbox-1",
            owner_user_id="owner-1",
            workspace_path="/workspace/demo",
            created_at=1.0,
        )


def test_workspace_row_requires_non_blank_workspace_path() -> None:
    with pytest.raises(ValueError, match="workspace.workspace_path must not be blank"):
        WorkspaceRow(
            id="workspace-1",
            sandbox_id="sandbox-1",
            owner_user_id="owner-1",
            workspace_path="  ",
            created_at=1.0,
        )
