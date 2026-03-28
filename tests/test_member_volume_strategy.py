"""Smoke test for member_volume_service orchestrator functions."""


def test_orchestrator_imports():
    from backend.web.services.member_volume_service import (
        get_lease_volume_source,
        setup_sandbox_mounts,
        save_file,
        list_volume_files,
        resolve_volume_file,
        delete_volume_file,
    )
    assert callable(get_lease_volume_source)
    assert callable(setup_sandbox_mounts)
