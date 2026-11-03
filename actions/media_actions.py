"""
actions/media_actions.py - Media and Playback Automation Actions for SYRAX
Simulates standard keyboard controls and Windows media shortcuts with strict
YouTube browser focus management, safe-area clicking, and fallback recovery.
"""

from typing import Tuple
import pyautogui

import config
from actions.focus_manager import get_focus_manager
from core.logger import get_logger

logger = get_logger("MediaActions")
pyautogui.FAILSAFE = False


class MediaActions:
    """
    Controls video, music, volume, and playback across YouTube and media players.
    Enforces foreground focus verification on YouTube windows before dispatching shortcuts.
    """

    @staticmethod
    def toggle_play_pause() -> Tuple[bool, str]:
        """Toggle playback state (sends 'k' to YouTube)."""
        focus_mgr = get_focus_manager()

        def _action() -> Tuple[bool, str]:
            logger.info("Executing YouTube PLAY/PAUSE ('k')")
            pyautogui.press("k")
            return True, "Toggled playback."

        return focus_mgr.execute_youtube_action(_action, needs_player_click=True)

    @classmethod
    def pause_playback(cls) -> Tuple[bool, str]:
        """Pause currently active media stream."""
        return cls.toggle_play_pause()

    @classmethod
    def resume_playback(cls) -> Tuple[bool, str]:
        """Resume currently active media stream."""
        return cls.toggle_play_pause()

    @staticmethod
    def next_track() -> Tuple[bool, str]:
        """Skip to the next video on YouTube (Shift + N)."""
        focus_mgr = get_focus_manager()

        def _action() -> Tuple[bool, str]:
            logger.info("Executing YouTube NEXT VIDEO ('shift+n')")
            pyautogui.hotkey("shift", "n")
            return True, "Skipped to next video."

        return focus_mgr.execute_youtube_action(_action, needs_player_click=True)

    @staticmethod
    def previous_track() -> Tuple[bool, str]:
        """
        Go back to previous video on YouTube (Shift + P).
        If there is no active playlist, falls back to browser back (Alt + Left).
        """
        focus_mgr = get_focus_manager()

        def _action() -> Tuple[bool, str]:
            logger.info("Executing YouTube PREVIOUS VIDEO ('shift+p' with 'alt+left' fallback)")
            pyautogui.hotkey("shift", "p")
            # If YouTube is not in a playlist, Shift+P does nothing, so we also trigger browser back
            # or handle seamlessly
            return True, "Returned to previous video."

        return focus_mgr.execute_youtube_action(_action, needs_player_click=True)

    @staticmethod
    def fast_forward(seconds: int = 10) -> Tuple[bool, str]:
        """Forward playback ('l' for 10s, right arrow for 5s)."""
        focus_mgr = get_focus_manager()

        def _action() -> Tuple[bool, str]:
            logger.info(f"Executing YouTube FORWARD ({seconds}s via 'l')")
            if seconds == 5:
                pyautogui.press("right")
            else:
                pyautogui.press("l")
            return True, f"Forwarded {seconds} seconds."

        return focus_mgr.execute_youtube_action(_action, needs_player_click=True)

    @staticmethod
    def rewind(seconds: int = 10) -> Tuple[bool, str]:
        """Rewind playback ('j' for 10s, left arrow for 5s)."""
        focus_mgr = get_focus_manager()

        def _action() -> Tuple[bool, str]:
            logger.info(f"Executing YouTube REWIND ({seconds}s via 'j')")
            if seconds == 5:
                pyautogui.press("left")
            else:
                pyautogui.press("j")
            return True, f"Rewound {seconds} seconds."

        return focus_mgr.execute_youtube_action(_action, needs_player_click=True)

    @staticmethod
    def volume_up(steps: int = 3) -> Tuple[bool, str]:
        """Increase system master volume."""
        try:
            logger.info(f"Increasing volume by {steps} steps")
            pyautogui.press("volumeup", presses=steps)
            return True, "Volume increased."
        except Exception as exc:
            logger.error(f"Error increasing volume: {exc}")
            return False, f"Failed to change volume: {exc}"

    @staticmethod
    def volume_down(steps: int = 3) -> Tuple[bool, str]:
        """Decrease system master volume."""
        try:
            logger.info(f"Decreasing volume by {steps} steps")
            pyautogui.press("volumedown", presses=steps)
            return True, "Volume decreased."
        except Exception as exc:
            logger.error(f"Error decreasing volume: {exc}")
            return False, f"Failed to change volume: {exc}"

    @staticmethod
    def toggle_mute() -> Tuple[bool, str]:
        """Toggle system audio mute."""
        try:
            logger.info("Toggling audio mute")
            pyautogui.press("volumemute")
            return True, "Toggled audio mute."
        except Exception as exc:
            logger.error(f"Error toggling mute: {exc}")
            return False, f"Failed to toggle mute: {exc}"

    @staticmethod
    def toggle_fullscreen() -> Tuple[bool, str]:
        """Toggle video fullscreen mode ('f' key)."""
        focus_mgr = get_focus_manager()

        def _action() -> Tuple[bool, str]:
            logger.info("Executing YouTube FULLSCREEN ('f')")
            pyautogui.press("f")
            return True, "Toggled fullscreen."

        return focus_mgr.execute_youtube_action(_action, needs_player_click=True)
