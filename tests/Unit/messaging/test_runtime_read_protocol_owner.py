from __future__ import annotations

import importlib
from typing import get_type_hints


def test_runtime_read_protocols_live_in_top_level_protocols_module() -> None:
    protocol_module = importlib.import_module("protocols.runtime_read")

    assert protocol_module.AgentThreadActivity.__module__ == "protocols.runtime_read"
    assert protocol_module.RuntimeThreadActivityReader.__module__ == "protocols.runtime_read"


def test_runtime_thread_selector_consumes_top_level_runtime_read_protocol() -> None:
    selector_module = importlib.import_module("messaging.delivery.runtime_thread_selector")
    protocol_module = importlib.import_module("protocols.runtime_read")

    hints = get_type_hints(selector_module.select_runtime_thread_for_recipient)

    assert hints["activity_reader"] is protocol_module.RuntimeThreadActivityReader
