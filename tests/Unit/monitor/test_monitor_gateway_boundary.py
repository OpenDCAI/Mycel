import inspect

from backend.web.routers import monitor, resources


def test_monitor_router_depends_on_gateway_not_internal_services():
    source = inspect.getsource(monitor)

    forbidden = (
        "from backend.web.services import monitor_service",
        "from backend.web.services import resource_service",
        "from backend.web.services.resource_cache import",
        "monitor_service.",
        "resource_service.",
        "get_resource_overview_snapshot",
        "refresh_resource_overview_sync",
    )
    for token in forbidden:
        assert token not in source

    assert "monitor_gateway." in source


def test_product_resource_router_depends_on_gateway_not_projection_service():
    source = inspect.getsource(resources)

    assert "resource_projection_service" not in source
    assert "monitor_gateway." in source
