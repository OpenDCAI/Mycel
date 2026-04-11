from storage.container import StorageContainer
from storage.providers.supabase.eval_batch_repo import SupabaseEvaluationBatchRepo
from storage.runtime import build_evaluation_batch_repo, build_storage_container


class _FakeClient:
    def table(self, _name):
        raise AssertionError("table() should not be touched during wiring-only tests")


def test_storage_container_exposes_evaluation_batch_repo():
    container = StorageContainer(supabase_client=_FakeClient())

    repo = container.evaluation_batch_repo()

    assert isinstance(repo, SupabaseEvaluationBatchRepo)


def test_runtime_builder_exposes_evaluation_batch_repo():
    repo = build_evaluation_batch_repo(supabase_client=_FakeClient())

    assert isinstance(repo, SupabaseEvaluationBatchRepo)


def test_build_storage_container_exposes_evaluation_batch_repo():
    container = build_storage_container(supabase_client=_FakeClient())

    repo = container.evaluation_batch_repo()

    assert isinstance(repo, SupabaseEvaluationBatchRepo)
