def is_virtual_thread_id(thread_id: str | None) -> bool:
    return bool(thread_id) and thread_id.startswith("(") and thread_id.endswith(")")
