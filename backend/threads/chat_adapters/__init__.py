"""Chat adapters — Chat<->Thread dispatch surface inside the threads domain.

Holds the adapters that translate between messaging.delivery envelopes
and thread execution. Formerly backend/agent_runtime/; folded into
threads/ because this is a threads-domain responsibility (see target
architecture §2 aggregate-root rule and §5.5 "agent_runtime absorbs").

IN:
    - gateway.py, port.py (transport facade)
    - chat_handler.py (chat -> thread dispatch implementation)
    - thread_handler.py (direct thread input)
    - chat_runtime_services.py (app-backed services)
    - activity_reader.py (implements protocols.runtime_read.
      RuntimeThreadActivityReader)
    - bootstrap.py (wires the gateway into app.state)

OUT:
    - Execution loop (threads/run/)
    - Runtime pool (threads/pool/)
    - History projection (threads/history.py, threads/projection.py)
"""
