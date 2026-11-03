"""
core/interrupt_manager.py - Global High-Priority Interrupt & Cancellation Manager
Provides instantaneous, pre-parser interrupt routing for Stop, Cancel, Pause, and Exit.
Employs threading.Event cancellation tokens, high-priority queuing, and immediate
Windows SAPI TTS purging so SYRAX stops on a dime.
"""

import queue
import re
import threading
from enum import Enum
from typing import Any, Callable, List, Optional

from core.event_bus import Events, get_event_bus
from core.logger import get_logger

logger = get_logger("InterruptManager")


class InterruptType(str, Enum):
    """Categorized interrupt signals."""
    STOP_ACTIVITY = "stop_activity"      # Stop playback, search, scroll loop, or current operation
    CANCEL_MESSAGE = "cancel_message"    # Abort pending WhatsApp message draft
    PAUSE = "pause"                      # Pause active media
    RESUME = "resume"                    # Resume active media
    STOP_GESTURES = "stop_gestures"      # Deactivate Gesture mode
    EXIT_SYRAX = "exit_syrax"            # Clean application shutdown (requires explicit phrase)
    NONE = "none"


class InterruptManager:
    """
    Central coordinator for high-priority user interruptions.
    Guarantees that 'Stop' immediately halts running tasks and TTS audio output.
    """

    # Fast keyword spotting regexes
    RE_PAUSE = re.compile(
        r"^(?:pause|pause\s+the\s+music|pause\s+video|pause\s+music|pause\s+playback|stop\s+music|stop\s+playback|hold(?:\s+video)?|पॉज़|रोक)$",
        re.IGNORECASE
    )

    RE_INTERRUPT_STOP = re.compile(
        r"^(?:stop|ruko|roko|ruk\s*jao|band\s*karo|cancel|halt|abort|freeze|close\s+the\s+current\s+activity|stop\s+current\s+activity|stop\s+it|stop\s+scrolling|रुको|रुक\s*जाओ|रोको|बंद\s*करो|ठहरो|रुक)$",
        re.IGNORECASE
    )

    RE_CANCEL_MESSAGE = re.compile(
        r"^(?:cancel\s*message|don'?t\s*send|do\s*not\s*send|mat\s*bhejo|clear\s*message|cancel\s*whatsapp(?:\s*operation)?|मत\s*भेजो|रद्द\s*करो)$",
        re.IGNORECASE
    )

    RE_STOP_GESTURES = re.compile(
        r"^(?:stop\s+gesture\s+mode|disable\s+gesture\s+mode|exit\s+gesture\s+mode|gesture\s+mode\s+off|जेस्चर\s+मोड\s+बंद\s*करो)$",
        re.IGNORECASE
    )

    RE_EXIT_APP = re.compile(
        r"^(?:exit\s+syrax|close\s+syrax|quit\s+syrax|shut\s*down\s+syrax|close\s+assistant|exit\s+assistant|goodbye|bye\s+syrax|alvida|अलविदा|सिरेक्स\s+बंद\s*करो|बाय\s+सिरेक्स)$",
        re.IGNORECASE
    )

    def __init__(self, tts_engine: Optional[Any] = None) -> None:
        self._event_bus = get_event_bus()
        self._tts_engine = tts_engine
        self._cancellation_token = threading.Event()
        self._priority_queue: queue.Queue[InterruptType] = queue.Queue()
        self._listeners: List[Callable[[InterruptType], None]] = []
        self._lock = threading.RLock()

    def set_tts_engine(self, tts_engine: Any) -> None:
        """Inject TTS engine reference for immediate speech purge on interrupt."""
        with self._lock:
            self._tts_engine = tts_engine

    def register_listener(self, callback: Callable[[InterruptType], None]) -> None:
        """Register a callback invoked immediately when an interrupt occurs."""
        with self._lock:
            self._listeners.append(callback)

    def check_for_interrupt_phrase(self, text: str) -> InterruptType:
        """
        Fast-path check evaluated BEFORE full natural language parsing.
        Returns InterruptType if the phrase matches an urgent interrupt, else InterruptType.NONE.
        """
        clean = text.strip().lower()
        if not clean:
            return InterruptType.NONE

        # 1. Exit Check (Must be explicit "Exit SYRAX" / "Close SYRAX")
        if self.RE_EXIT_APP.match(clean):
            return InterruptType.EXIT_SYRAX

        # 2. Stop Gestures
        if self.RE_STOP_GESTURES.match(clean):
            return InterruptType.STOP_GESTURES

        # 3. Cancel WhatsApp Message
        if self.RE_CANCEL_MESSAGE.match(clean):
            return InterruptType.CANCEL_MESSAGE

        # 4. Pause Playback Check
        if self.RE_PAUSE.match(clean):
            return InterruptType.PAUSE

        # 5. Stop Current Activity
        if self.RE_INTERRUPT_STOP.match(clean):
            return InterruptType.STOP_ACTIVITY

        # Word-boundary check for raw single-word utterances ("stop", "ruko", "pause")
        tokens = clean.split()
        if len(tokens) == 1:
            if tokens[0] in ("pause",):
                return InterruptType.PAUSE
            if tokens[0] in ("stop", "ruko", "roko", "cancel", "halt"):
                return InterruptType.STOP_ACTIVITY

        return InterruptType.NONE

    def trigger_interrupt(self, interrupt_type: InterruptType = InterruptType.STOP_ACTIVITY, reason: str = "User voice interrupt") -> None:
        """
        Execute high-priority interrupt sequence:
        1. Set cancellation token.
        2. Purge TTS audio output instantly.
        3. Enqueue to priority queue.
        4. Notify all registered action workers.
        """
        logger.info(f"HIGH-PRIORITY INTERRUPT: {interrupt_type.value} ({reason})")

        # 1. Flag active cancellation token
        self._cancellation_token.set()

        # 2. Immediately stop & purge active TTS synthesizer
        if self._tts_engine:
            try:
                if hasattr(self._tts_engine, "purge"):
                    self._tts_engine.purge()
                else:
                    self._tts_engine.stop_speaking()
            except Exception as tts_err:
                logger.debug(f"Error purging TTS on interrupt: {tts_err}")

        # 3. Add to priority queue
        self._priority_queue.put(interrupt_type)

        # 4. Emit system interrupt event
        self._event_bus.emit(
            Events.ACTIVITY_LOG,
            category="SYSTEM",
            message=f"Interrupt triggered: {interrupt_type.value}"
        )

        # 5. Notify local listeners
        with self._lock:
            for listener in self._listeners:
                try:
                    listener(interrupt_type)
                except Exception as cb_err:
                    logger.error(f"Error in interrupt listener: {cb_err}")

    def is_cancelled(self) -> bool:
        """Return True if an interrupt has been signaled for active operations."""
        return self._cancellation_token.is_set()

    def is_interrupted(self) -> bool:
        """Convenience alias for is_cancelled."""
        return self._cancellation_token.is_set()

    def reset_token(self) -> None:
        """Reset cancellation token before launching a new operation."""
        self._cancellation_token.clear()

    def clear_interrupt(self) -> None:
        """Convenience alias for reset_token."""
        self._cancellation_token.clear()

    def get_token(self) -> threading.Event:
        """Provide direct reference to cancellation Event for worker loops."""
        return self._cancellation_token
