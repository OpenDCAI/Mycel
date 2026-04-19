import inspect

from backend.monitor.api.http import router as monitor_router_impl
from backend.monitor.infrastructure.web import gateway as monitor_gateway_impl
from backend.web.routers import monitor, resources
from backend.web.services import monitor_gateway


def test_monitor_router_depends_on_gateway_not_internal_services():
    source = inspect.getsource(monitor_router_impl)
    broad_shell = "monitor" + "_service"

    forbidden = (
        "from backend.web.services import resource_service",
        "from backend.web.services.resource_cache import",
        f"{broad_shell}.",
        "resource_service.",
        "get_resource_overview_snapshot",
        "refresh_resource_overview_sync",
    )
    for token in forbidden:
        assert token not in source

    assert "monitor_gateway." in source


def test_monitor_router_web_shell_delegates_to_monitor_module():
    source = inspect.getsource(monitor)

    assert "backend.monitor.api.http.router" in source


def test_product_resource_router_depends_on_gateway_not_projection_service():
    source = inspect.getsource(resources)

    assert "resource_projection_service" not in source
    assert "monitor_gateway." in source


def test_monitor_gateway_depends_on_resource_boundary_not_resource_internals():
    source = inspect.getsource(monitor_gateway_impl)

    forbidden = (
        "    resource_projection_service,",
        "    resource_service,",
        "from backend.web.services.resource_cache import",
        "\n    return resource_service.",
        "\n    return resource_projection_service.",
        "get_resource_overview_snapshot",
        "refresh_resource_overview_sync",
    )
    for token in forbidden:
        assert token not in source

    assert "monitor_resource_service" in source


def test_monitor_gateway_web_shell_delegates_to_monitor_module():
    source = inspect.getsource(monitor_gateway)

    assert "backend.monitor.infrastructure.web" in source
