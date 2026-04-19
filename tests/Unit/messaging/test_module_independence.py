from __future__ import annotations

import inspect

from messaging import service as messaging_service_module
from messaging.delivery import dispatcher as delivery_dispatcher_module


def test_messaging_core_modules_do_not_import_backend_web_serializers() -> None:
    service_source = inspect.getsource(messaging_service_module)
    dispatcher_source = inspect.getsource(delivery_dispatcher_module)

    assert "backend.web.utils.serializers" not in service_source
    assert "backend.web.utils.serializers" not in dispatcher_source
