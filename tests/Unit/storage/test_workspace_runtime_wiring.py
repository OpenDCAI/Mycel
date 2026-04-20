from storage.container import StorageContainer
from storage.runtime import build_storage_container, build_workspace_repo


class _FakeClient:
    def table(self, _name):
        raise AssertionError("table() should not be touched during wiring-only tests")


def test_storage_container_exposes_workspace_repo() -> None:
    container = StorageContainer(supabase_client=_FakeClient())

    assert container.workspace_repo().__class__.__name__ == "SupabaseWorkspaceRepo"


def test_runtime_builder_exposes_workspace_repo() -> None:
    repo = build_workspace_repo(supabase_client=_FakeClient())

    assert repo.__class__.__name__ == "SupabaseWorkspaceRepo"


def test_build_storage_container_exposes_workspace_repo() -> None:
    container = build_storage_container(supabase_client=_FakeClient())

    assert container.workspace_repo().__class__.__name__ == "SupabaseWorkspaceRepo"
