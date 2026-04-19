import inspect

from backend.monitor.api.http import global_router, web_local_router
from backend.monitor.api.http import router as monitor_router_impl
from backend.monitor.infrastructure.web import gateway as monitor_gateway_impl
from backend.web import main as web_main
from backend.web.routers import resources


def test_monitor_router_depends_on_gateway_not_internal_services():
    aggregate_source = inspect.getsource(monitor_router_impl)
    global_source = inspect.getsource(global_router)
    web_local_source = inspect.getsource(web_local_router)
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
        assert token not in aggregate_source
        assert token not in global_source
        assert token not in web_local_source

    assert "monitor_gateway." in global_source
    assert "monitor_gateway." in web_local_source
    assert "backend.web.core.dependencies" not in aggregate_source


def test_web_backend_points_at_monitor_router_module():
    source = inspect.getsource(web_main)

    assert "backend.web.routers import (" not in source or "monitor," not in source
    assert "backend.monitor.api.http import router as monitor_router" in source
    assert "app.include_router(monitor_router.router)" in source


def test_monitor_router_composes_global_and_web_local_buckets():
    source = inspect.getsource(monitor_router_impl)

    assert "from backend.monitor.api.http import global_router, web_local_router" in source
    assert "router.include_router(global_router.router)" in source
    assert "router.include_router(web_local_router.router)" in source
    assert '@router.get("/threads")' not in source
    assert '@router.get("/resources")' not in source


def test_product_resource_router_depends_on_gateway_not_projection_service():
    source = inspect.getsource(resources)

    assert "resource_projection_service" not in source
    assert "monitor_gateway." in source
    assert "backend.web.services import monitor_gateway" not in source
    assert "backend.monitor.infrastructure.web import gateway as monitor_gateway" in source


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

    assert "monitor_resources" in source


def test_product_resource_router_points_at_monitor_gateway_module():
    source = inspect.getsource(resources)

    assert "backend.monitor.infrastructure.web" in source
