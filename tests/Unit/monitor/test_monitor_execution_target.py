from types import SimpleNamespace

import pytest

from backend.monitor.api.http.execution_target import resolve_monitor_evaluation_base_url


def _request(*, title: str, hostname: str = "testserver", scheme: str = "http"):
    return SimpleNamespace(
        app=SimpleNamespace(title=title),
        url=SimpleNamespace(hostname=hostname, scheme=scheme),
        base_url=f"{scheme}://{hostname}",
    )


def test_monitor_evaluation_target_uses_request_base_url_on_web_app(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("LEON_MONITOR_EVALUATION_BASE_URL", raising=False)
    request = _request(title="Mycel Web Backend")

    assert resolve_monitor_evaluation_base_url(request) == "http://testserver"


def test_monitor_evaluation_target_uses_backend_port_for_monitor_app(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("LEON_MONITOR_EVALUATION_BASE_URL", raising=False)
    monkeypatch.setattr(
        "backend.monitor.api.http.execution_target.resolve_app_port",
        lambda *_args, **_kwargs: 8010,
    )
    request = _request(title="Mycel Monitor Backend")

    assert resolve_monitor_evaluation_base_url(request) == "http://127.0.0.1:8010"


def test_monitor_evaluation_target_requires_explicit_env_for_nonlocal_monitor_host(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("LEON_MONITOR_EVALUATION_BASE_URL", raising=False)
    monkeypatch.setattr(
        "backend.monitor.api.http.execution_target.resolve_app_port",
        lambda *_args, **_kwargs: 8010,
    )
    request = _request(title="Mycel Monitor Backend", hostname="monitor.example.com", scheme="https")

    with pytest.raises(RuntimeError, match="LEON_MONITOR_EVALUATION_BASE_URL"):
        resolve_monitor_evaluation_base_url(request)
