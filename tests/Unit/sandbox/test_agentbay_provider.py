from types import SimpleNamespace

from sandbox.providers.agentbay import AgentBayProvider


def _provider_with_fake_client(fake_client) -> AgentBayProvider:
    provider = AgentBayProvider.__new__(AgentBayProvider)
    provider.name = "agentbay"
    provider.client = fake_client
    provider.default_context_path = "/home/wuying"
    provider.image_id = None
    provider._sessions = {}
    provider._capability = AgentBayProvider.CAPABILITY
    return provider


def test_create_session_refreshes_agentbay_session_when_direct_call_fields_missing():
    raw_session = SimpleNamespace(session_id="sess-123", token="", link_url="", mcpTools=[])
    hydrated_session = SimpleNamespace(session_id="sess-123", token="tok", link_url="https://link", mcpTools=[object()])
    fake_client = SimpleNamespace(
        context=SimpleNamespace(get=lambda *args, **kwargs: None),
        create=lambda params: SimpleNamespace(success=True, session=raw_session, error_message=""),
        get=lambda session_id: SimpleNamespace(success=True, session=hydrated_session, error_message=""),
    )
    provider = _provider_with_fake_client(fake_client)

    info = provider.create_session()

    assert info.session_id == "sess-123"
    assert provider._sessions["sess-123"] is hydrated_session


def test_get_session_refreshes_stale_cached_agentbay_session():
    stale_session = SimpleNamespace(session_id="sess-123", token="", link_url="", mcpTools=[])
    hydrated_session = SimpleNamespace(session_id="sess-123", token="tok", link_url="https://link", mcpTools=[object()])
    fake_client = SimpleNamespace(
        get=lambda session_id: SimpleNamespace(success=True, session=hydrated_session, error_message=""),
    )
    provider = _provider_with_fake_client(fake_client)
    provider._sessions["sess-123"] = stale_session

    session = provider._get_session("sess-123")

    assert session is hydrated_session
    assert provider._sessions["sess-123"] is hydrated_session
