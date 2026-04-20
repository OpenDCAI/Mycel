"""Display state builder — single source of truth for ChatEntry[].

Contains builder.py (~800 LOC) that replaces two frontend state machines
(message-mapper.ts + use-stream-handler.ts) with one Python module.
Both GET (refresh) and SSE (streaming) produce entries from this builder.

GET  -> build_from_checkpoint() or get_entries() -> full entries[]
SSE  -> apply_event()                             -> display_delta
"""
