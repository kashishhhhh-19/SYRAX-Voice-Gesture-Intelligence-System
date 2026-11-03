"""
actions/presentation_actions.py - Slide & Browser Navigation for SYRAX
Simulates slide transitions, zoom gestures, and scrolling with foreground
verification to ensure zooming and scrolling apply safely to the intended active application.
"""

from typing import Tuple
import pyautogui

import config
from actions.focus_manager import get_focus_manager
from core.logger import get_logger

logger = get_logger("PresentationActions")
pyautogui.FAILSAFE = True


class PresentationActions:
    """Handles PowerPoint, Google Slides, page scrolling, and viewport zoom."""

    @staticmethod
    def _is_safe_foreground() -> bool:
        """Ensure input is not sent to the SYRAX dashboard itself."""
        focus_mgr = get_focus_manager()
        fg_hwnd = focus_mgr.get_foreground_window()
        if not fg_hwnd:
            return True
        title = (focus_mgr.get_window_text(fg_hwnd) or "").lower()
        if "syrax" in title or "gesture intelligence" in title:
            logger.debug(f"Action skipped: SYRAX dashboard window is foreground ('{title}').")
            return False
        return True

    @classmethod
    def next_slide(cls) -> Tuple[bool, str]:
        """Advance to the next slide."""
        if not cls._is_safe_foreground():
            return False, "Dashboard is focused; action blocked."
        try:
            logger.info("Executing NEXT SLIDE action")
            pyautogui.press("right")
            return True, "Next slide."
        except Exception as exc:
            logger.error(f"Error advancing slide: {exc}")
            return False, f"Failed next slide: {exc}"

    @classmethod
    def previous_slide(cls) -> Tuple[bool, str]:
        """Navigate back to the previous slide."""
        if not cls._is_safe_foreground():
            return False, "Dashboard is focused; action blocked."
        try:
            logger.info("Executing PREVIOUS SLIDE action")
            pyautogui.press("left")
            return True, "Previous slide."
        except Exception as exc:
            logger.error(f"Error reverting slide: {exc}")
            return False, f"Failed previous slide: {exc}"

    @classmethod
    def zoom_in(cls) -> Tuple[bool, str]:
        """Zoom in viewport (Ctrl + Plus), respecting safe foreground."""
        if not cls._is_safe_foreground():
            return False, "Dashboard is focused; action blocked."
        try:
            logger.info("Executing ZOOM IN (Ctrl + Plus)")
            pyautogui.hotkey("ctrl", "=")
            return True, "Zoomed in."
        except Exception as exc:
            logger.error(f"Error zooming in: {exc}")
            return False, f"Failed zoom in: {exc}"

    @classmethod
    def zoom_out(cls) -> Tuple[bool, str]:
        """Zoom out viewport (Ctrl + Minus), respecting safe foreground."""
        if not cls._is_safe_foreground():
            return False, "Dashboard is focused; action blocked."
        try:
            logger.info("Executing ZOOM OUT (Ctrl + Minus)")
            pyautogui.hotkey("ctrl", "-")
            return True, "Zoomed out."
        except Exception as exc:
            logger.error(f"Error zooming out: {exc}")
            return False, f"Failed zoom out: {exc}"

    @classmethod
    def reset_zoom(cls) -> Tuple[bool, str]:
        """Reset viewport zoom (Ctrl + 0)."""
        if not cls._is_safe_foreground():
            return False, "Dashboard is focused; action blocked."
        try:
            logger.info("Executing RESET ZOOM (Ctrl + 0)")
            pyautogui.hotkey("ctrl", "0")
            return True, "Zoom reset."
        except Exception as exc:
            logger.error(f"Error resetting zoom: {exc}")
            return False, f"Failed reset zoom: {exc}"

    @classmethod
    def scroll(cls, direction: str, amount: int = config.SCROLL_STEP) -> Tuple[bool, str]:
        """
        Scroll active application up or down smoothly.
        Ensures input is never sent while SYRAX dashboard has focus.
        """
        if not cls._is_safe_foreground():
            return False, "Dashboard is focused; scroll blocked."

        delta = amount if direction.lower() == "up" else -amount
        try:
            logger.debug(f"Executing SCROLL {direction} (delta: {delta})")
            pyautogui.scroll(delta)
            return True, f"Scrolled {direction}."
        except Exception as exc:
            logger.error(f"Error executing scroll: {exc}")
            return False, f"Failed scroll: {exc}"
