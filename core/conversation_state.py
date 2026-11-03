"""
core/conversation_state.py - Contextual Multi-Turn Conversation State Manager
Tracks active application, conversation turns, pending slots (e.g. missing song or message),
and confirmation states (e.g. WhatsApp send confirmation).
"""

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class PendingConfirmation:
    """State of an action awaiting explicit user confirmation (e.g. WhatsApp message send)."""
    action_type: str                  # e.g. "whatsapp_send"
    recipient: str                    # e.g. "Rahul"
    content: str                      # e.g. "how are you"
    created_at: float = field(default_factory=time.time)
    timeout_seconds: float = 30.0     # Auto-expires after 30s for safety

    def is_expired(self) -> bool:
        return (time.time() - self.created_at) > self.timeout_seconds


class ConversationState:
    """
    Thread-safe contextual state holder for multi-turn conversational workflows.
    Maintains active application, pending slot filling, confirmation gates,
    and conversational memory (last video query, contact, clarification items).
    """

    CONTEXT_EXPIRATION_SECONDS = 60.0

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.active_app: str = "general"                 # "youtube", "instagram", "whatsapp", "general"
        self.last_intent: Optional[str] = None
        self.last_entities: Dict[str, Any] = {}
        self.last_video_query: Optional[str] = None
        self.last_contact: Optional[str] = None
        self.last_updated_at: float = time.time()

        self.pending_slot: Optional[str] = None          # e.g. "song_title", "message_content", "contact_name"
        self.pending_intent: Optional[str] = None        # Intent awaiting the missing slot
        self.pending_data: Dict[str, Any] = {}
        self.pending_confirmation: Optional[PendingConfirmation] = None
        self.pending_clarification: Optional[Dict[str, Any]] = None  # e.g. multiple video choices or contacts

    def touch(self) -> None:
        """Refresh context timestamp."""
        with self._lock:
            self.last_updated_at = time.time()

    def is_context_active(self, timeout: Optional[float] = None) -> bool:
        """Check if conversational context is within expiration limit."""
        with self._lock:
            limit = timeout or self.CONTEXT_EXPIRATION_SECONDS
            return (time.time() - self.last_updated_at) <= limit

    def set_active_app(self, app_name: str) -> None:
        """Update active application context."""
        with self._lock:
            self.active_app = app_name.lower().strip()
            self.touch()

    def get_active_app(self) -> str:
        """Return current active application name."""
        with self._lock:
            return self.active_app

    def update_video_context(self, query: str) -> None:
        """Remember last played video or search query for follow-up references."""
        with self._lock:
            self.last_video_query = query
            self.active_app = "youtube"
            self.touch()

    def update_contact_context(self, contact: str) -> None:
        """Remember last messaged or searched contact."""
        with self._lock:
            self.last_contact = contact
            self.active_app = "whatsapp"
            self.touch()

    def set_pending_clarification(self, clarification_type: str, options: List[Any], data: Optional[Dict[str, Any]] = None) -> None:
        """Store multiple options requiring user disambiguation."""
        with self._lock:
            self.pending_clarification = {
                "type": clarification_type,
                "options": options,
                "data": data or {},
                "timestamp": time.time()
            }
            self.touch()

    def get_pending_clarification(self) -> Optional[Dict[str, Any]]:
        """Retrieve active clarification, auto-clearing if older than 30s."""
        with self._lock:
            if self.pending_clarification:
                if (time.time() - self.pending_clarification.get("timestamp", 0)) > 30.0:
                    self.pending_clarification = None
                    return None
                return self.pending_clarification
            return None

    def clear_pending_clarification(self) -> None:
        with self._lock:
            self.pending_clarification = None

    def set_pending_slot(self, slot_name: str, intent: str, initial_data: Optional[Dict[str, Any]] = None) -> None:
        """Prompt user for a missing slot (e.g., 'What song would you like to hear?')."""
        with self._lock:
            self.pending_slot = slot_name
            self.pending_intent = intent
            self.pending_data = initial_data or {}

    def get_pending_slot(self) -> Optional[Tuple[str, str, Dict[str, Any]]]:
        """Return (slot_name, intent, data) if a slot is currently awaited."""
        with self._lock:
            if self.pending_slot and self.pending_intent:
                return (self.pending_slot, self.pending_intent, self.pending_data)
            return None

    def clear_pending_slot(self) -> None:
        """Clear active slot expectation."""
        with self._lock:
            self.pending_slot = None
            self.pending_intent = None
            self.pending_data = {}

    def set_pending_confirmation(self, action_type: str, recipient: str, content: str) -> None:
        """Hold a message/action in memory pending explicit spoken confirmation."""
        with self._lock:
            self.pending_confirmation = PendingConfirmation(
                action_type=action_type,
                recipient=recipient,
                content=content
            )

    def get_pending_confirmation(self) -> Optional[PendingConfirmation]:
        """Retrieve active pending confirmation, auto-clearing if expired."""
        with self._lock:
            if self.pending_confirmation:
                if self.pending_confirmation.is_expired():
                    self.pending_confirmation = None
                    return None
                return self.pending_confirmation
            return None

    def clear_pending_confirmation(self) -> None:
        """Wipe pending confirmation (e.g. after send or on cancel)."""
        with self._lock:
            self.pending_confirmation = None

    def reset_all_pending(self) -> None:
        """Full reset of pending dialogs on interrupt or stop."""
        with self._lock:
            self.clear_pending_slot()
            self.clear_pending_confirmation()


# Global Singleton
_global_conversation_state: Optional[ConversationState] = None
_cs_lock = threading.Lock()


def get_conversation_state() -> ConversationState:
    """Retrieve global ConversationState singleton."""
    global _global_conversation_state
    with _cs_lock:
        if _global_conversation_state is None:
            _global_conversation_state = ConversationState()
        return _global_conversation_state
