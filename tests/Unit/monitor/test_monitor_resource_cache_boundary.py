from backend.monitor.infrastructure.resources import resource_overview_cache as resource_cache


def test_web_resource_cache_is_only_a_compatibility_shell():
    assert resource_cache.__name__ == "backend.monitor.infrastructure.resources.resource_overview_cache"
