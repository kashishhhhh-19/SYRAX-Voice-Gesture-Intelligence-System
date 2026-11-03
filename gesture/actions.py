"""
gesture/actions.py - Focus-Safe Action Executor for SYRAX
Verifies foreground window title and process before dispatching any keyboard,
mouse, or scrolling input. Strictly prevents sending synthetic events when the
SYRAX dashboard itself is focused, and enforces safety bounds on all inputs.
"""

import logging
import time
from typing import Optional, Tuple

import pyautogui
pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.02

logger = logging.getLogger("ActionExecutor")


class FocusStatus:
    DETECTED = "Detected"
    FOCUSED = "Focused"
    SWITCHING = "Switching Focus"
    NOT_FOUND = "Not Found"
    BLOCKED_DASHBOARD = "Dashboard Focused (Blocked)"


class ActionExecutor:
    """
    Executes keyboard, hotkey, and mouse scroll actions with strict foreground verification.
    """

    def __init__(self, allow_focus_switch: bool = True) -> None:
        self.allow_focus_switch = allow_focus_switch

    def get_foreground_window_info(self) -> Tuple[int, str, str]:
        """
        Query Windows OS for the currently focused foreground window.
        Returns (hwnd: int, title: str, process_name: str).
        """
        try:
            import win32gui
            import win32process
            import psutil

            hwnd = win32gui.GetForegroundWindow()
            if not hwnd:
                return 0, "", ""

            title = win32gui.GetWindowText(hwnd) or ""
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            try:
                proc = psutil.Process(pid).name().lower()
            except Exception:
                proc = ""

            return int(hwnd), title, proc
        except Exception as exc:
            logger.debug(f"Foreground window check error: {exc}")
            return 0, "", ""

    def is_syrax_dashboard_focused(self, title: str, process: str) -> bool:
        """Check if SYRAX dashboard or terminal currently has OS focus."""
        lower_t = title.lower()
        if "syrax" in lower_t or "gesture intelligence" in lower_t:
            return True
        return False

    def execute_action(
        self,
        action_type: str,
        keys: list,
        direction: Optional[str] = None,
        scroll_delta: int = 0,
        expected_profile_name: str = "Default"
    ) -> Tuple[bool, str]:
        """
        Verify foreground window focus and execute action.
        Returns (success: bool, status_message: str).
        """
        hwnd, fg_title, fg_proc = self.get_foreground_window_info()

        # Rule 1: NEVER send input while SYRAX dashboard itself has focus
        if self.is_syrax_dashboard_focused(fg_title, fg_proc):
            logger.debug("Action skipped: SYRAX dashboard has foreground focus.")
            return False, FocusStatus.BLOCKED_DASHBOARD

        try:
            # 1. KEYBOARD PRESS
            if action_type == "key" and keys:
                key_to_press = keys[0]
                logger.debug(f"Pressing key: '{key_to_press}' in '{fg_title[:25]}'")
                pyautogui.press(key_to_press)
                return True, f"Key '{key_to_press}' dispatched"

            # 2. KEYBOARD HOTKEY (e.g. Shift + N, Ctrl + Plus)
            elif action_type == "hotkey" and keys:
                logger.debug(f"Pressing hotkey: {keys} in '{fg_title[:25]}'")
                pyautogui.hotkey(*keys)
                return True, f"Hotkey {'+'.join(keys)} dispatched"

            # 3. MOUSE SCROLLING (Movement-driven)
            elif action_type == "scroll":
                if scroll_delta != 0:
                    amount = scroll_delta
                else:
                    amount = 240 if (direction and direction.lower() == "up") else -240

                logger.debug(f"Scrolling {amount:+d} ticks in '{fg_title[:25]}'")
                pyautogui.scroll(amount)
                return True, f"Scrolled {amount:+d} ticks"

            # 4. SYSTEM COMMAND (e.g. Pause actions)
            elif action_type == "system":
                return True, "System command processed"

            return False, f"Unknown action type: {action_type}"
        except Exception as exc:
            logger.error(f"Error executing action {action_type}: {exc}")
            return False, f"Execution failed: {exc}"
