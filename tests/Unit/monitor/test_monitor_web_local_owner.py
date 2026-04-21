import importlib
import inspect


def test_web_backend_does_not_mount_empty_monitor_web_local_router() -> None:
    web_main_source = inspect.getsource(importlib.import_module("backend.web.main"))

    assert "web_local_router" not in web_main_source
