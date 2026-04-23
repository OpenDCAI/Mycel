from __future__ import annotations

import importlib
from typing import get_type_hints


def test_runtime_read_protocols_live_in_top_level_protocols_module() -> None:
    protocol_module = importlib.import_module("protocols.runtime_read")

    assert protocol_module.AgentThreadActivity.__module__ == "protocols.runtime_read"
    assert protocol_module.RuntimeThreadActivityReader.__module__ == "protocols.runtime_read"


def test_runtime_thread_selector_consumes_top_level_runtime_read_protocol() -> None:
    owner_reads_module = importlib.import_module("backend.threads.owner_reads")
    protocol_module = importlib.import_module("protocols.runtime_read")

    hints = get_type_hints(owner_reads_module._thread_running)

    assert hints["activity_reader"] is protocol_module.RuntimeThreadActivityReader
