import pytest

from storage.providers.supabase.lease_repo import SupabaseLeaseRepo
from tests.fakes.supabase import FakeSupabaseClient


def test_supabase_lease_repo_adopt_instance_fails_loudly_if_bootstrap_reload_missing():
    repo = SupabaseLeaseRepo(client=FakeSupabaseClient(tables={"sandbox_leases": [], "sandbox_instances": []}))
    rows = iter([None, None])

    repo.create = lambda **_kwargs: {  # type: ignore[method-assign]
        "lease_id": "lease-1",
        "provider_name": "test-provider",
    }
    repo.get = lambda _lease_id: next(rows)  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="failed to load lease after adopt_instance bootstrap"):
        repo.adopt_instance(
            lease_id="lease-1",
            provider_name="test-provider",
            instance_id="inst-123",
        )
