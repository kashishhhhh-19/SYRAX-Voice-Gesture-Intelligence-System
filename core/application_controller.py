"""
core/application_controller.py - Application-Aware Contextual Router for SYRAX
Tracks the user's active foreground application and disambiguates generic commands
(e.g., 'next', 'previous', 'stop', 'play') based on what the user is currently looking at.
"""

import threading
import time
from enum import Enum
from typing import Optional, Tuple

import config
from actions.focus_manager import get_focus_manager
from actions.instagram_actions import get_instagram_actions
from actions.media_actions import MediaActions
from actions.presentation_actions import PresentationActions
from actions.youtube_actions import get_youtube_actions
from core.conversation_state import get_conversation_state
from core.event_bus import Events, get_event_bus
from core.logger import get_logger

logger = get_logger("ApplicationController")


class AppContext(str, Enum):
    """Categorized foreground application contexts."""
    YOUTUBE = "youtube"
    INSTAGRAM = "instagram"
    WHATSAPP = "whatsapp"
    BROWSER = "browser"
    SYRAX = "syrax"
    GENERAL = "general"


class ApplicationController:
    """
    Monitors and detects active foreground application.
    Routes context-sensitive actions accordingly.
    """

    def __init__(self, focus_manager=None) -> None:
        self.focus_manager = focus_manager or get_focus_manager()
        self.conversation_state = get_conversation_state()
        self._event_bus = get_event_bus()
        self._current_context = AppContext.GENERAL
        self._last_detected_title = ""
        self._lock = threading.RLock()

    def detect_foreground_app(self) -> AppContext:
        """
        Inspect OS active foreground window and categorize into AppContext.
        Updates conversation state and emits Events.ACTIVE_APP_CHANGED on transition.
        """
        adapter = self.focus_manager._adapter
        try:
            fg_hwnd = adapter.get_foreground_window()
            if not fg_hwnd:
                return self._current_context

            title = adapter.get_window_text(fg_hwnd) or ""
            lower = title.lower()

            new_context = AppContext.GENERAL
            if "youtube" in lower:
                new_context = AppContext.YOUTUBE
            elif "instagram" in lower:
                new_context = AppContext.INSTAGRAM
            elif "whatsapp" in lower:
                new_context = AppContext.WHATSAPP
            elif "syrax" in lower:
                new_context = AppContext.SYRAX
            elif any(b in lower for b in ("chrome", "edge", "firefox", "brave", "opera", "vivaldi")):
                # Check if recent conversation context specified an active app
                active = self.conversation_state.get_active_app()
                if active == "youtube":
                    new_context = AppContext.YOUTUBE
                elif active == "instagram":
                    new_context = AppContext.INSTAGRAM
                elif active == "whatsapp":
                    new_context = AppContext.WHATSAPP
                else:
                    new_context = AppContext.BROWSER

            with self._lock:
                if new_context != self._current_context or title != self._last_detected_title:
                    self._current_context = new_context
                    self._last_detected_title = title
                    self.conversation_state.set_active_app(new_context.value)
                    self._event_bus.emit(
                        Events.ACTIVE_APP_CHANGED,
                        app=new_context.value,
                        title=title
                    )

            return new_context
        except Exception as exc:
            logger.debug(f"Error detecting foreground app: {exc}")
            return self._current_context

    def get_current_context(self) -> AppContext:
        with self._lock:
            return self._current_context

    def set_current_context(self, context: AppContext) -> None:
        with self._lock:
            self._current_context = context
            self.conversation_state.set_active_app(context.value)

    def route_context_action(self, action_name: str) -> Tuple[bool, str, Optional[str]]:
        """
        Dispatches context-sensitive action ('next', 'previous', 'pause', 'resume')
        to the appropriate application handler based on foreground app.
        """
        ctx = self.detect_foreground_app()
        logger.info(f"Routing contextual action '{action_name}' in context: {ctx.value}")

        # 1. YouTube Context
        if ctx == AppContext.YOUTUBE:
            yt = get_youtube_actions()
            if action_name == "next":
                success, msg = yt.next_video()
                return success, msg, "Next video."
            elif action_name in ("previous", "prev"):
                success, msg = yt.previous_video()
                return success, msg, "Previous video."
            elif action_name == "pause":
                success, msg = yt.pause()
                return success, msg, "Video paused."
            elif action_name == "resume":
                success, msg = yt.resume()
                return success, msg, "Video resumed."
            elif action_name == "stop":
                success, msg = yt.pause()
                return success, msg, "Playback stopped."

        # 2. Instagram Context
        elif ctx == AppContext.INSTAGRAM:
            ig = get_instagram_actions()
            if action_name == "next":
                success, msg = ig.next_reel()
                return success, msg, "Next reel."
            elif action_name in ("previous", "prev"):
                success, msg = ig.previous_reel()
                return success, msg, "Previous reel."
            elif action_name in ("pause", "resume", "toggle"):
                success, msg = ig.play_pause_reel()
                return success, msg, "Reel playback toggled."
            elif action_name == "stop":
                success, msg = ig.play_pause_reel()
                return success, msg, "Reel stopped."

        # 3. Fallback to General Media / Presentation controls
        if action_name == "next":
            success, msg = MediaActions.next_track()
            return success, msg, "Next."
        elif action_name in ("previous", "prev"):
            success, msg = MediaActions.previous_track()
            return success, msg, "Previous."
        elif action_name == "pause":
            success, msg = MediaActions.pause_playback()
            return success, msg, "Paused."
        elif action_name == "resume":
            success, msg = MediaActions.resume_playback()
            return success, msg, "Resumed."
        elif action_name == "stop":
            success, msg = MediaActions.pause_playback()
            return success, msg, "Stopped."

        return False, f"Unknown action: {action_name}", None


# Global Singleton
_global_app_controller: Optional[ApplicationController] = None
_ac_lock = threading.Lock()


def get_application_controller() -> ApplicationController:
    """Retrieve the global ApplicationController singleton."""
    global _global_app_controller
    with _ac_lock:
        if _global_app_controller is None:
            _global_app_controller = ApplicationController()
        return _global_app_controller
