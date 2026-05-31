"""In-memory message bus for inter-agent handoff, keyed by agent name."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class BusMessage:
    sender: str
    content: str


class MessageBus:
    def __init__(self) -> None:
        self._queues: dict[str, list[BusMessage]] = {}

    def enqueue(self, target: str, message: BusMessage) -> None:
        self._queues.setdefault(target, []).append(message)

    def drain(self, target: str) -> list[BusMessage]:
        messages = self._queues.get(target, [])
        self._queues[target] = []
        return messages

    def pending(self, target: str) -> int:
        return len(self._queues.get(target, []))
