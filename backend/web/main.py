from backend.bootstrap.app_entrypoint import load_env_file_from_env, resolve_app_port, run_reloadable_app

load_env_file_from_env()

from backend.web.app_factory import create_app  # noqa: E402

app = create_app()


if __name__ == "__main__":
    # @@@port-precedence - git worktree config > LEON_BACKEND_PORT > PORT > 8001
    port = resolve_app_port("LEON_BACKEND_PORT", "worktree.ports.backend", 8001)
    # @@@module-launch-target - Package-qualified target keeps module launch (`python -m backend.web.main`) import-safe.
    # @@@reload-dirs - restrict file watching to backend + core + config + storage only.
    # Without this, StatReload scans .venv/, node_modules/, .git/ etc. and burns 50-80% CPU.
    run_reloadable_app(
        "backend.web.main:app",
        port=port,
        reload_dirs=["backend", "core", "config", "storage", "sandbox", "messaging"],
    )
