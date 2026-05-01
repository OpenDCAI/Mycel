from __future__ import annotations

import hashlib
import json
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RuntimeInboxFrame:
    type: str
    seq: int
    fingerprint: str
    ts: float
    metadata: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "seq": self.seq,
            "fingerprint": self.fingerprint,
            "ts": self.ts,
            "metadata": self.metadata,
        }


class RuntimeInboxStreamState:
    def __init__(self, *, replay_limit: int = 256) -> None:
        self._replay_limit = replay_limit
        self._seq_by_user: dict[str, int] = defaultdict(int)
        self._frames_by_user: dict[str, deque[RuntimeInboxFrame]] = defaultdict(lambda: deque(maxlen=replay_limit))
        self._lock = threading.Lock()

    def assign(self, user_id: str, notifications: list[dict[str, Any]]) -> list[dict[str, Any]]:
        sequenced: list[dict[str, Any]] = []
        with self._lock:
            for notification in notifications:
                self._seq_by_user[user_id] += 1
                seq = self._seq_by_user[user_id]
                metadata = dict(notification)
                sequenced_item = {"seq": seq, **metadata}
                self._frames_by_user[user_id].append(
                    RuntimeInboxFrame(
                        type="notify",
                        seq=seq,
                        fingerprint=fingerprint_runtime_notification(metadata),
                        ts=time.time(),
                        metadata=metadata,
                    )
                )
                sequenced.append(sequenced_item)
        return sequenced

    def replay_since(self, user_id: str, since_seq: int) -> list[dict[str, Any]]:
        with self._lock:
            frames = list(self._frames_by_user[user_id])
        if frames and since_seq < frames[0].seq - 1:
            return [
                {
                    "type": "replay_overflow",
                    "since_seq": since_seq,
                    "oldest_seq": frames[0].seq,
                }
            ]
        return [frame.as_dict() for frame in frames if frame.seq > since_seq]

    def frames_between(self, user_id: str, *, after_seq: int, through_seq: int) -> list[dict[str, Any]]:
        with self._lock:
            frames = list(self._frames_by_user[user_id])
        return [frame.as_dict() for frame in frames if after_seq < frame.seq <= through_seq]


def fingerprint_runtime_notification(metadata: dict[str, Any]) -> str:
    payload = json.dumps(metadata, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
