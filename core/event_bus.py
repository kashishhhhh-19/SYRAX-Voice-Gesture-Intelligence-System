"""
core/event_bus.py - Decoupled Asynchronous Event Bus for SYRAX
Enables thread-safe, decoupled communication between Voice, Gesture,
GUI, and Action Dispatcher components.
"""

import threading
from collections import defaultdict
from typing import Any, Callable, Dict, List, Optional

from core.logger import get_logger

logger = get_logger("EventBus")


class Events:
    """Event identifier constants used throughout SYRAX."""
    # Voice Events
    VOICE_STATUS_CHANGED = "VOICE_STATUS_CHANGED"
    VOICE_RECOGNIZED = "VOICE_RECOGNIZED"
    VOICE_SPEECH_START = "VOICE_SPEECH_START"
    VOICE_SPEECH_END = "VOICE_SPEECH_END"
    VOICE_DEVICE_CHANGED = "VOICE_DEVICE_CHANGED"
    VOICE_ERROR = "VOICE_ERROR"

    # Gesture Events
    GESTURE_STATUS_CHANGED = "GESTURE_STATUS_CHANGED"
    GESTURE_FRAME = "GESTURE_FRAME"
    GESTURE_DETECTED = "GESTURE_DETECTED"
    GESTURE_ERROR = "GESTURE_ERROR"

    # Action & Execution Events
    ACTION_EXECUTED = "ACTION_EXECUTED"
    ASSISTANT_RESPONSE = "ASSISTANT_RESPONSE"
    YOUTUBE_FOCUS_CHANGED = "YOUTUBE_FOCUS_CHANGED"
    GESTURE_MODE_TOGGLED = "GESTURE_MODE_TOGGLED"
    ACTIVE_APP_CHANGED = "ACTIVE_APP_CHANGED"

    # WhatsApp & Social Events
    WHATSAPP_CONFIRMATION_PENDING = "WHATSAPP_CONFIRMATION_PENDING"
    WHATSAPP_MESSAGE_SENT = "WHATSAPP_MESSAGE_SENT"
    WHATSAPP_MESSAGE_CANCELLED = "WHATSAPP_MESSAGE_CANCELLED"
    INSTAGRAM_STATUS_CHANGED = "INSTAGRAM_STATUS_CHANGED"

    # System & Diagnostics Events
    SYSTEM_STATUS_CHANGED = "SYSTEM_STATUS_CHANGED"
    ACTIVITY_LOG = "ACTIVITY_LOG"
    DIAGNOSTIC_RESULT = "DIAGNOSTIC_RESULT"
    SHUTDOWN_REQUESTED = "SHUTDOWN_REQUESTED"


class EventBus:
    """
    Thread-safe publisher/subscriber event bus.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._subscribers: Dict[str, List[Callable[..., Any]]] = defaultdict(list)

    def subscribe(self, event_name: str, callback: Callable[..., Any]) -> None:
        """
        Register a subscriber callback for the specified event.
        """
        with self._lock:
            if callback not in self._subscribers[event_name]:
                self._subscribers[event_name].append(callback)
                logger.debug(f"Subscribed {callback.__name__ if hasattr(callback, '__name__') else callback} to '{event_name}'")

    def unsubscribe(self, event_name: str, callback: Callable[..., Any]) -> None:
        """
        Remove a subscriber callback from the specified event.
        """
        with self._lock:
            if callback in self._subscribers[event_name]:
                self._subscribers[event_name].remove(callback)
                logger.debug(f"Unsubscribed from '{event_name}'")

    def emit(self, event_name: str, **kwargs: Any) -> None:
        """
        Publish an event to all registered subscribers.
        Executes callbacks safely without crashing on individual subscriber failure.
        """
        with self._lock:
            callbacks = list(self._subscribers.get(event_name, []))

        for callback in callbacks:
            try:
                callback(**kwargs)
            except Exception as exc:
                logger.error(f"Error executing callback for event '{event_name}': {exc}", exc_info=True)

    def clear(self) -> None:
        """Remove all event subscriptions."""
        with self._lock:
            self._subscribers.clear()


# Global Singleton Instance
_global_event_bus: Optional[EventBus] = None
_bus_lock = threading.Lock()


def get_event_bus() -> EventBus:
    """Retrieve the global EventBus singleton."""
    global _global_event_bus
    with _bus_lock:
        if _global_event_bus is None:
            _global_event_bus = EventBus()
        return _global_event_bus
