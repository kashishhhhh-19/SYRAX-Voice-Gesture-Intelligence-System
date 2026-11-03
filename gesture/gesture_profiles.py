"""
gesture/gesture_profiles.py - Application-Specific Gesture Profiles for SYRAX
Enforces isolation between YouTube, Instagram Reels, and Presentation slide gestures.
Prevents cross-application shortcut leakage and coordinates context-sensitive hand control.
"""

from abc import ABC, abstractmethod
from typing import Optional, Tuple

import config
from actions.instagram_actions import get_instagram_actions
from actions.media_actions import MediaActions
from actions.presentation_actions import PresentationActions
from core.logger import get_logger

logger = get_logger("GestureProfiles")


class BaseGestureProfile(ABC):
    """Abstract base class for all application gesture profiles."""

    def __init__(self, name: str) -> None:
        self.name = name

    @abstractmethod
    def handle_gesture(self, gesture_name: str) -> Tuple[bool, str, Optional[str]]:
        """
        Execute the gesture action according to this profile.
        Returns (success: bool, description: str, spoken_text: Optional[str]).
        """
        pass


class YouTubeGestureProfile(BaseGestureProfile):
    """Gesture mapping for YouTube video playback and page navigation."""

    def __init__(self) -> None:
        super().__init__("YouTube")

    def handle_gesture(self, gesture_name: str) -> Tuple[bool, str, Optional[str]]:
        # 1. Steady Open Palm -> Play / Pause ("k")
        if gesture_name == "OPEN_PALM_STEADY":
            success, msg = MediaActions.toggle_play_pause()
            spoken = "Playback paused."
            return success, "Play / Pause", spoken if success else None

        # 2. Swipe Right -> Next Video (Shift + N)
        if gesture_name == "SWIPE_RIGHT":
            success, msg = MediaActions.next_track()
            spoken = config.RESPONSES["gesture_video_next"][0]
            return success, "Next Video", spoken if success else None

        # 3. Swipe Left -> Previous Video (Shift + P / Alt + Left)
        if gesture_name == "SWIPE_LEFT":
            success, msg = MediaActions.previous_track()
            spoken = config.RESPONSES["gesture_video_prev"][0]
            return success, "Previous Video", spoken if success else None

        # 4. Two-Finger Moving Right -> Forward 10s ("l")
        if gesture_name == "TWO_FINGER_RIGHT":
            success, msg = MediaActions.fast_forward(10)
            spoken = config.RESPONSES["gesture_video_forward"][0]
            return success, "Forwarding", spoken if success else None

        # 5. Two-Finger Moving Left -> Rewind 10s ("j")
        if gesture_name == "TWO_FINGER_LEFT":
            success, msg = MediaActions.rewind(10)
            spoken = config.RESPONSES["gesture_video_rewind"][0]
            return success, "Rewinding", spoken if success else None

        # 6. One Finger Upward -> Scroll Page Down
        if gesture_name == "ONE_FINGER_UP":
            success, msg = PresentationActions.scroll("down")
            return success, "Scroll Down", None

        # 7. One Finger Downward -> Scroll Page Up
        if gesture_name == "ONE_FINGER_DOWN":
            success, msg = PresentationActions.scroll("up")
            return success, "Scroll Up", None

        # 8. Pinch Out -> Zoom In
        if gesture_name == "PINCH_OUT":
            success, msg = PresentationActions.zoom_in()
            spoken = config.RESPONSES["gesture_zoom_in"][0]
            return success, "Zoom In", spoken if success else None

        # 9. Pinch In -> Zoom Out
        if gesture_name == "PINCH_IN":
            success, msg = PresentationActions.zoom_out()
            spoken = config.RESPONSES["gesture_zoom_out"][0]
            return success, "Zoom Out", spoken if success else None

        return False, f"Unhandled YouTube gesture: {gesture_name}", None


class InstagramGestureProfile(BaseGestureProfile):
    """Gesture mapping for Instagram Reels browsing."""

    def __init__(self) -> None:
        super().__init__("Instagram")
        self.instagram_actions = get_instagram_actions()

    def handle_gesture(self, gesture_name: str) -> Tuple[bool, str, Optional[str]]:
        # 1. Steady Open Palm -> Play / Pause Reel (Spacebar)
        if gesture_name == "OPEN_PALM_STEADY":
            success, msg = self.instagram_actions.play_pause_reel()
            return success, "Reel Play/Pause", None

        # 2. One Finger Up or Swipe Down -> Next Reel (Down arrow)
        if gesture_name in ("ONE_FINGER_UP", "SWIPE_DOWN"):
            success, msg = self.instagram_actions.next_reel()
            return success, "Next Reel", None

        # 3. One Finger Down or Swipe Up -> Previous Reel (Up arrow)
        if gesture_name in ("ONE_FINGER_DOWN", "SWIPE_UP"):
            success, msg = self.instagram_actions.previous_reel()
            return success, "Previous Reel", None

        # 4. Zoom In / Out
        if gesture_name == "PINCH_OUT":
            success, msg = PresentationActions.zoom_in()
            return success, "Zoom In", None

        if gesture_name == "PINCH_IN":
            success, msg = PresentationActions.zoom_out()
            return success, "Zoom Out", None

        return False, f"Unhandled Instagram gesture: {gesture_name}", None


class PresentationGestureProfile(BaseGestureProfile):
    """Gesture mapping for Presentation Slides (PowerPoint, Google Slides)."""

    def __init__(self) -> None:
        super().__init__("Presentation")

    def handle_gesture(self, gesture_name: str) -> Tuple[bool, str, Optional[str]]:
        if gesture_name in ("SWIPE_RIGHT", "ONE_FINGER_RIGHT"):
            success, msg = PresentationActions.next_slide()
            return success, "Next Slide", None

        if gesture_name in ("SWIPE_LEFT", "ONE_FINGER_LEFT"):
            success, msg = PresentationActions.previous_slide()
            return success, "Previous Slide", None

        if gesture_name == "PINCH_OUT":
            success, msg = PresentationActions.zoom_in()
            return success, "Zoom In", None

        if gesture_name == "PINCH_IN":
            success, msg = PresentationActions.zoom_out()
            return success, "Zoom Out", None

        return False, f"Unhandled Presentation gesture: {gesture_name}", None
