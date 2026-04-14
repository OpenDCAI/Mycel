from storage.container import StorageContainer
from storage.runtime import build_sandbox_repo, build_storage_container


class _FakeClient:
    def table(self, _name):
        raise AssertionError("table() should not be touched during wiring-only tests")

    def schema(self, _name):
        return self


def test_storage_container_exposes_sandbox_repo() -> None:
    container = StorageContainer(supabase_client=_FakeClient())

    assert container.sandbox_repo().__class__.__name__ == "SupabaseSandboxRepo"


def test_runtime_builder_exposes_sandbox_repo() -> None:
    repo = build_sandbox_repo(supabase_client=_FakeClient())

    assert repo.__class__.__name__ == "SupabaseSandboxRepo"


def test_build_storage_container_exposes_sandbox_repo() -> None:
    container = build_storage_container(supabase_client=_FakeClient())

    assert container.sandbox_repo().__class__.__name__ == "SupabaseSandboxRepo"
