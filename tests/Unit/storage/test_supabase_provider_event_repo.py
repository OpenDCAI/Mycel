from storage.providers.supabase.provider_event_repo import SupabaseProviderEventRepo
from tests.fakes.supabase import FakeSupabaseClient


def test_supabase_provider_event_repo_uses_observability_schema_table() -> None:
    tables: dict[str, list[dict]] = {"observability.provider_events": []}
    repo = SupabaseProviderEventRepo(FakeSupabaseClient(tables=tables))

    repo.record(
        provider_name="daytona",
        instance_id="instance-1",
        event_type="started",
        payload={"ok": True},
        matched_lease_id="lease-1",
        matched_sandbox_id="sandbox-1",
    )

    row = tables["observability.provider_events"][0]
    assert row["provider_name"] == "daytona"
    assert row["matched_lease_id"] == "lease-1"
    assert row["matched_sandbox_id"] == "sandbox-1"
    assert "provider_events" not in tables
