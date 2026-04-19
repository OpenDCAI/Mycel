"""Compatibility shell for thread runtime event store helpers."""

from backend.thread_runtime import event_store as _owner

_default_run_event_repo = None
build_storage_container = _owner.build_storage_container
RunEventReadTransport = _owner.RunEventReadTransport
build_run_event_read_transport = _owner.build_run_event_read_transport
cleanup_old_runs = _owner.cleanup_old_runs
get_last_seq = _owner.get_last_seq
get_latest_run_id = _owner.get_latest_run_id
get_run_start_seq = _owner.get_run_start_seq


async def append_event(*args, **kwargs):
    _owner._default_run_event_repo = _default_run_event_repo
    _owner.build_storage_container = build_storage_container
    return await _owner.append_event(*args, **kwargs)


async def read_events_after(*args, **kwargs):
    _owner._default_run_event_repo = _default_run_event_repo
    _owner.build_storage_container = build_storage_container
    return await _owner.read_events_after(*args, **kwargs)
