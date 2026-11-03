"""
gesture/gesture_actions.py - Dispatcher and Cooldown Manager for Hand Gestures
Maps recognized hand gestures into YouTube playback, page scrolling, and viewport zoom actions.
Includes focus management enforcement, voice announcement throttling, and active state gating.
"""

import time
from typing import Dict, Optional, Tuple

import config
from actions.media_actions import MediaActions
from actions.presentation_actions import PresentationActions
from core.event_bus import Events, get_event_bus
from core.logger import get_logger
from gesture.gesture_profiles import (
    BaseGestureProfile,
    InstagramGestureProfile,
    PresentationGestureProfile,
    YouTubeGestureProfile,
)

logger = get_logger("GestureActions")


class GestureActions:
    """
    Executes automation actions triggered by hand gestures across YouTube, Instagram, and Presentations.
    Maintains per-gesture cooldown timers, active profile routing, and throttles spoken announcements.
    """

    def __init__(self, profile: Optional[BaseGestureProfile] = None) -> None:
        self._event_bus = get_event_bus()
        self._active_profile: BaseGestureProfile = profile or YouTubeGestureProfile()
        self._last_trigger_times: Dict[str, float] = {}
        self._last_announcement_time: float = 0.0
        self._last_announced_phrase: str = ""

    def get_active_profile(self) -> BaseGestureProfile:
        """Return the current gesture profile."""
        return self._active_profile

    def set_profile(self, profile: BaseGestureProfile) -> None:
        """Set active gesture profile."""
        logger.info(f"Switching gesture profile to: {profile.name}")
        self._active_profile = profile

    def set_profile_by_name(self, name: str) -> None:
        """Switch profile by friendly name ('youtube', 'instagram', 'presentation')."""
        lower = name.lower()
        if "insta" in lower:
            self.set_profile(InstagramGestureProfile())
        elif "pres" in lower or "slide" in lower:
            self.set_profile(PresentationGestureProfile())
        else:
            self.set_profile(YouTubeGestureProfile())

    def is_cooling_down(self, gesture_name: str, cooldown: Optional[float] = None) -> bool:
        """Check if gesture is within its debounce cooldown window."""
        now = time.time()
        last = self._last_trigger_times.get(gesture_name, 0.0)
        limit = cooldown if cooldown is not None else config.GESTURE_COOLDOWN_SECONDS
        return (now - last) < limit

    def record_trigger(self, gesture_name: str) -> None:
        """Record the timestamp of an executed gesture."""
        self._last_trigger_times[gesture_name] = time.time()

    def _should_speak(self, phrase: Optional[str]) -> bool:
        """
        Check if spoken confirmation should be voiced:
        - Must be enabled in config
        - Must have phrase
        - Throttled to prevent rapid repeat announcements
        """
        if not phrase or not config.GESTURE_VOICE_FEEDBACK_ENABLED:
            return False

        now = time.time()
        if (now - self._last_announcement_time) < config.GESTURE_VOICE_ANNOUNCEMENT_THROTTLE_SECONDS:
            if phrase == self._last_announced_phrase:
                return False

        self._last_announcement_time = now
        self._last_announced_phrase = phrase
        return True

    def execute_gesture(self, gesture_name: str, state: str) -> Tuple[bool, str, Optional[str]]:
        """
        Execute YouTube action corresponding to gesture_name and current state.
        Returns (success: bool, description: str, spoken_response: Optional[str]).
        """
        # 1. State Machine Mode Toggle (Fist hold ~1.0s)
        if gesture_name in ("FIST_TOGGLE", "FIST"):
            if gesture_name == "FIST_TOGGLE":
                # Toggle state between ACTIVE and IDLE
                new_state = config.GESTURE_STATE_IDLE if state == config.GESTURE_STATE_ACTIVE else config.GESTURE_STATE_ACTIVE
                self.record_trigger("FIST_TOGGLE")
                if new_state == config.GESTURE_STATE_ACTIVE:
                    spoken = config.RESPONSES["gesture_activated"][0]
                    return True, "Gesture Mode Activated", spoken if self._should_speak(spoken) else None
                else:
                    spoken = config.RESPONSES["gesture_exited"][0]
                    return True, "Gesture Mode Paused", spoken if self._should_speak(spoken) else None
            return False, "Holding Fist...", None

        # 2. Open Palm when IDLE does not trigger actions
        if state != config.GESTURE_STATE_ACTIVE:
            return False, "Ignored (Gesture Mode is OFF)", None

        # ======================================================================
        # ACTIVE PROFILE GESTURE EXECUTION
        # ======================================================================
        cooldown = config.GESTURE_COOLDOWN_SECONDS
        if "SCROLL" in gesture_name or "ONE_FINGER" in gesture_name:
            cooldown = config.SCROLL_REPEAT_INTERVAL
        elif "PINCH" in gesture_name:
            cooldown = config.PINCH_REPEAT_INTERVAL
        elif "TWO_FINGER" in gesture_name:
            cooldown = config.TWO_FINGER_COOLDOWN_SECONDS
        elif "SWIPE" in gesture_name:
            cooldown = config.SWIPE_COOLDOWN_SECONDS

        if self.is_cooling_down(gesture_name, cooldown):
            return False, "Cooldown", None

        self.record_trigger(gesture_name)
        success, desc, spoken = self._active_profile.handle_gesture(gesture_name)
        return success, desc, (spoken if (success and self._should_speak(spoken)) else None)
