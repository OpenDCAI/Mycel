import os
import subprocess

from fastapi.middleware.cors import CORSMiddleware

from backend import app_entrypoint


def test_resolve_app_port_prefers_env_key(monkeypatch):
    monkeypatch.setenv("LEON_BACKEND_PORT", "8010")
    monkeypatch.setenv("PORT", "9000")

    assert app_entrypoint.resolve_app_port("LEON_BACKEND_PORT", "worktree.ports.backend", 8001) == 8010


def test_resolve_app_port_uses_worktree_config_when_env_missing(monkeypatch):
    monkeypatch.delenv("LEON_BACKEND_PORT", raising=False)
    monkeypatch.delenv("PORT", raising=False)

    def _run(*_args, **_kwargs):
        return subprocess.CompletedProcess(
            args=["git", "config"],
            returncode=0,
            stdout="8012\n",
            stderr="",
        )

    monkeypatch.setattr(app_entrypoint.subprocess, "run", _run)

    assert app_entrypoint.resolve_app_port("LEON_BACKEND_PORT", "worktree.ports.backend", 8001) == 8012


def test_load_env_file_from_env_loads_dotenv(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("HELLO_ENTRYPOINT=world\n")
    monkeypatch.setenv("ENV_FILE", str(env_file))
    monkeypatch.delenv("HELLO_ENTRYPOINT", raising=False)

    app_entrypoint.load_env_file_from_env()

    assert os.environ["HELLO_ENTRYPOINT"] == "world"


def test_add_permissive_cors_registers_cors_middleware():
    calls: list[tuple[object, dict[str, object]]] = []

    class _App:
        def add_middleware(self, middleware_cls, **kwargs):
            calls.append((middleware_cls, kwargs))

    app = _App()

    app_entrypoint.add_permissive_cors(app)

    assert calls == [
        (
            CORSMiddleware,
            {
                "allow_origins": ["*"],
                "allow_credentials": True,
                "allow_methods": ["*"],
                "allow_headers": ["*"],
            },
        )
    ]
