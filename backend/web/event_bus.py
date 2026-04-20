"""Web compatibility export surface for the neutral event bus owner."""

from backend import event_bus as _event_bus

EventBus = _event_bus.EventBus
EventCallback = _event_bus.EventCallback
Unsubscribe = _event_bus.Unsubscribe


def get_event_bus() -> EventBus:
    return _event_bus.get_event_bus()


__all__ = ["EventBus", "EventCallback", "Unsubscribe", "get_event_bus"]
