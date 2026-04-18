"""Provider runtime inventory read port for Monitor."""

from __future__ import annotations

from typing import Any

from backend.web.services import sandbox_service


def load_provider_orphan_runtime_rows() -> list[dict[str, Any]]:
    _, managers = sandbox_service.init_providers_and_managers()
    return sandbox_service.load_provider_orphan_runtimes(managers)
