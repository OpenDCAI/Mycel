def test_all_providers_accept_thread_id():
    """Verify all providers accept thread_id in create_session()."""
    import inspect
    from sandbox.providers.docker import DockerProvider
    from sandbox.providers.local import LocalSessionProvider
    from sandbox.providers.daytona import DaytonaProvider
    from sandbox.providers.e2b import E2BProvider
    from sandbox.providers.agentbay import AgentBayProvider

    providers = [DockerProvider, LocalSessionProvider, DaytonaProvider, E2BProvider, AgentBayProvider]

    for provider_class in providers:
        sig = inspect.signature(provider_class.create_session)
        params = sig.parameters

        assert 'context_id' in params, f"{provider_class.__name__} missing context_id"
        assert 'thread_id' in params, f"{provider_class.__name__} missing thread_id"
