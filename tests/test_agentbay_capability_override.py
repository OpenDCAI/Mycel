import sys
import types

from sandbox.providers.agentbay import AgentBayProvider


def _install_fake_agentbay_module(monkeypatch) -> None:
    fake_mod = types.ModuleType("agentbay")

    class FakeAgentBay:
        def __init__(self, api_key: str):
            self.api_key = api_key

    fake_mod.AgentBay = FakeAgentBay
    monkeypatch.setitem(sys.modules, "agentbay", fake_mod)


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
