from __future__ import annotations

import json
import logging
import re
import threading
import time
from collections.abc import Callable, Generator
from typing import Any

logger = logging.getLogger(__name__)
_CHANNEL_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
DEFAULT_POSTGRES_WAKE_CHANNEL = "mycel_runtime_inbox_wake"


class RuntimeInboxWakeBus:
    def __init__(self) -> None:
        self._handlers: dict[str, Callable[[], None]] = {}
        self._lock = threading.Lock()

    def register(self, inbox_id: str, handler: Callable[[], None]) -> None:
        with self._lock:
            self._handlers[inbox_id] = handler

    def unregister(self, inbox_id: str) -> None:
        with self._lock:
            self._handlers.pop(inbox_id, None)

    def publish(self, inbox_id: str) -> None:
        with self._lock:
            handler = self._handlers.get(inbox_id)
        if not handler:
            return
        try:
            handler()
        except Exception:
            logger.exception("Runtime inbox wake handler raised for %s", inbox_id)


class PostgresRuntimeInboxWakeBus(RuntimeInboxWakeBus):
    def __init__(
        self,
        pg_url: str,
        *,
        connect: Callable[..., Any] | None = None,
        channel: str = DEFAULT_POSTGRES_WAKE_CHANNEL,
    ) -> None:
        super().__init__()
        self._pg_url = pg_url
        self._connect = connect
        self._channel = _validate_channel(channel)
        self._listener_lock = threading.Lock()
        self._listener_started = False

    def register(
        self,
        inbox_id: str,
        handler: Callable[[], None],
        *,
        start_listener: bool = True,
    ) -> None:
        super().register(inbox_id, handler)
        if start_listener:
            self._ensure_listener()

    def publish(self, inbox_id: str) -> None:
        super().publish(inbox_id)
        payload = json.dumps({"inbox_id": inbox_id}, ensure_ascii=False, separators=(",", ":"))
        with self._connect_pg() as conn:
            conn.execute("SELECT pg_notify(%s, %s)", (self._channel, payload))

    def dispatch_payload(self, payload: str) -> None:
        try:
            data = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Invalid runtime inbox wake payload") from exc
        inbox_id = data.get("inbox_id") if isinstance(data, dict) else None
        if not isinstance(inbox_id, str) or not inbox_id:
            raise RuntimeError("Invalid runtime inbox wake payload")
        super().publish(inbox_id)

    def _ensure_listener(self) -> None:
        with self._listener_lock:
            if self._listener_started:
                return
            thread = threading.Thread(
                target=self._listen_forever,
                name="runtime-inbox-postgres-wake",
                daemon=True,
            )
            thread.start()
            self._listener_started = True

    def _listen_forever(self) -> None:
        while True:
            try:
                with self._connect_pg() as conn:
                    conn.execute(f"LISTEN {self._channel}")
                    while True:
                        for item in _iter_notifies(conn.notifies(timeout=30.0)):
                            self.dispatch_payload(str(item.payload))
            except Exception:
                logger.exception("Runtime inbox Postgres wake listener failed")
                time.sleep(1.0)

    def _connect_pg(self) -> Any:
        if self._connect is not None:
            return self._connect(self._pg_url, autocommit=True)
        import psycopg

        return psycopg.connect(self._pg_url, autocommit=True)


def _iter_notifies(notifies: Generator[Any]) -> Generator[Any]:
    yield from notifies


def _validate_channel(channel: str) -> str:
    if not _CHANNEL_RE.match(channel):
        raise RuntimeError("Invalid Postgres notification channel")
    return channel
