import sys
import types
from typing import Any, cast

from sandbox.providers.agentbay import AgentBayProvider


def _install_fake_agentbay_module(monkeypatch) -> None:
    fake_mod = cast(Any, types.ModuleType("agentbay"))
    fake_api_mod = cast(Any, types.ModuleType("agentbay.api"))
    fake_api_models_mod = cast(Any, types.ModuleType("agentbay.api.models"))

    class FakeAgentBay:
        def __init__(self, api_key: str):
            self.api_key = api_key

    class FakeCreateSessionParams:
        def __init__(self):
            self.image_id = None
            self.context_syncs = None

    class FakeContextSync:
        @staticmethod
        def new(context_id: str, path: str):
            return {"context_id": context_id, "path": path}

    class FakeGetSessionRequest:
        def __init__(self, authorization: str, session_id: str):
            self.authorization = authorization
            self.session_id = session_id

    fake_mod.AgentBay = FakeAgentBay
    fake_mod.CreateSessionParams = FakeCreateSessionParams
    fake_mod.ContextSync = FakeContextSync
    fake_api_models_mod.GetSessionRequest = FakeGetSessionRequest
    monkeypatch.setitem(sys.modules, "agentbay", fake_mod)
    monkeypatch.setitem(sys.modules, "agentbay.api", fake_api_mod)
    monkeypatch.setitem(sys.modules, "agentbay.api.models", fake_api_models_mod)


def test_agentbay_capability_default_from_class(monkeypatch):
    _install_fake_agentbay_module(monkeypatch)
    provider = AgentBayProvider(api_key="dummy")
    cap = provider.get_capability()
    declared = AgentBayProvider.CAPABILITY

    assert cap.can_pause == declared.can_pause
    assert cap.can_resume == declared.can_resume
    assert cap.can_destroy == declared.can_destroy
    assert cap.resource_capabilities == declared.resource_capabilities


def test_agentbay_capability_instance_override(monkeypatch):
    _install_fake_agentbay_module(monkeypatch)
    provider = AgentBayProvider(
        api_key="dummy",
        supports_pause=False,
        supports_resume=False,
    )
    cap = provider.get_capability()

    assert cap.can_pause is False
    assert cap.can_resume is False
    assert cap.can_destroy is True
    assert cap.resource_capabilities == AgentBayProvider.CAPABILITY.resource_capabilities


def test_agentbay_screenshot_uses_current_sdk_method(monkeypatch):
    _install_fake_agentbay_module(monkeypatch)
    provider = AgentBayProvider(api_key="dummy")

    class _ScreenshotResult:
        success = True
        data = "https://example.com/screenshot.png"

    class _FakeComputer:
        def screenshot(self):
            return _ScreenshotResult()

    class _FakeSession:
        def __init__(self) -> None:
            self.session_id = "sess-1"
            self.token = "tok"
            self.link_url = "https://link"
            self.mcpTools = [object()]
            self.computer = _FakeComputer()

    provider._sessions["sess-1"] = _FakeSession()
    screenshot = provider.screenshot("sess-1")
    assert screenshot == "https://example.com/screenshot.png"
