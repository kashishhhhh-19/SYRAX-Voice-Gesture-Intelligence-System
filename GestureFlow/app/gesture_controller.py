"""
GestureFlow - Computer Control Module
Executes simulated keyboard and mouse commands using PyAutoGUI.
Enforces strict safety controls, mode separation, failsafes, and an emergency stop.
"""

import time
from dataclasses import dataclass
from enum import Enum
from typing import Callable, List, Optional

try:
    import pyautogui
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.02
except ImportError:
    pyautogui = None

from app.config import ControlConfig
from app.gesture_recognition import GestureType, GestureResult


class ControlMode(Enum):
    PRESENTATION = "Presentation Navigation"
    SCROLLING = "General Scrolling"
    UNIFIED = "Unified Controller"


@dataclass
class ActionLogEntry:
    """Record of an executed action for the UI activity log."""
    timestamp: str
    gesture: str
    action: str
    mode: str
    status: str


class GestureController:
    """
    Translates recognized hand gestures into safe, user-authorized computer inputs.
    Strictly prevents execution unless explicitly enabled by the user.
    """

    def __init__(
        self,
        config: Optional[ControlConfig] = None,
        on_action_callback: Optional[Callable[[ActionLogEntry], None]] = None,
        action_executor: Optional[Callable[[str, str], bool]] = None
    ):
        self.config = config or ControlConfig()
        self.on_action_callback = on_action_callback
        self.action_executor = action_executor

        self.is_enabled: bool = self.config.enabled_by_default
        self.current_mode: ControlMode = ControlMode.UNIFIED
        self.action_history: List[ActionLogEntry] = []
        self.total_actions_executed: int = 0
        self.last_action_desc: str = "Ready"

        # Initialize PyAutoGUI failsafe
        if pyautogui is not None:
            pyautogui.FAILSAFE = self.config.pyautogui_failsafe
            pyautogui.PAUSE = self.config.pyautogui_pause

    def enable_control(self) -> None:
        """Explicitly enables computer actions."""
        self.is_enabled = True
        self._record_log("System", "Controls ENABLED by user", "Success")

    def disable_control(self) -> None:
        """Disables computer actions safely."""
        self.is_enabled = False
        self._record_log("System", "Controls DISABLED safely", "Safe")

    def emergency_stop(self) -> None:
        """Prominent kill-switch to immediately abort all computer controls."""
        self.is_enabled = False
        self.last_action_desc = "EMERGENCY STOP TRIGGERED"
        self._record_log("EMERGENCY", "All computer controls halted immediately", "HALTED")

    def set_mode(self, mode: ControlMode) -> None:
        """Changes the active control mode."""
        self.current_mode = mode
        self._record_log("Mode Change", f"Switched to {mode.value}", "Active")

    def process_gesture(self, result: GestureResult) -> Optional[ActionLogEntry]:
        """
        Evaluates a recognized gesture result.
        Executes the mapped keyboard/mouse action if authorized and triggered.
        """
        # Safety gate: If gesture is not triggered by recognizer, do nothing
        if not result.is_triggered:
            return None

        gesture = result.gesture

        # Always allow OPEN_PALM to pause or safely disable control
        if gesture == GestureType.OPEN_PALM:
            if self.is_enabled:
                self.is_enabled = False
                return self._record_log(
                    gesture.value,
                    "Open Palm detected: Computer controls paused safely",
                    "Paused"
                )

        # Allow FIST to activate controls or wake up if in Presentation or Unified mode
        if gesture == GestureType.FIST:
            if not self.is_enabled:
                self.is_enabled = True
                return self._record_log(
                    gesture.value,
                    "Fist detected: Activated presentation control mode",
                    "Activated"
                )

        # If controls are not enabled, reject all other actions
        if not self.is_enabled:
            return None

        # Mode-specific dispatch
        entry = None
        if self.current_mode == ControlMode.PRESENTATION:
            entry = self._handle_presentation_mode(gesture)
        elif self.current_mode == ControlMode.SCROLLING:
            entry = self._handle_scrolling_mode(gesture)
        elif self.current_mode == ControlMode.UNIFIED:
            entry = self._handle_unified_mode(gesture)

        return entry

    def _handle_presentation_mode(self, gesture: GestureType) -> Optional[ActionLogEntry]:
        """Maps presentation gestures: Next slide, Prev slide, Zoom In."""
        if gesture == GestureType.SWIPE_RIGHT:
            self._press_key("right")
            return self._record_log(gesture.value, "Next Slide (Right Arrow)", "Executed")

        elif gesture == GestureType.SWIPE_LEFT:
            self._press_key("left")
            return self._record_log(gesture.value, "Previous Slide (Left Arrow)", "Executed")

        elif gesture == GestureType.PINCH_OUT:
            self._hotkey("ctrl", "+")
            return self._record_log(gesture.value, "Zoom In (Ctrl + Plus)", "Executed")

        return None

    def _handle_scrolling_mode(self, gesture: GestureType) -> Optional[ActionLogEntry]:
        """Maps scrolling gestures: Scroll Up, Scroll Down."""
        if gesture == GestureType.POINTING_UP:
            self._scroll(self.config.scroll_amount)
            return self._record_log(gesture.value, f"Scroll Up (+{self.config.scroll_amount}px)", "Executed")

        elif gesture == GestureType.POINTING_DOWN:
            self._scroll(-self.config.scroll_amount)
            return self._record_log(gesture.value, f"Scroll Down (-{self.config.scroll_amount}px)", "Executed")

        return None

    def _handle_unified_mode(self, gesture: GestureType) -> Optional[ActionLogEntry]:
        """Handles both presentation and general navigation gestures."""
        # Presentation
        if gesture == GestureType.SWIPE_RIGHT:
            self._press_key("right")
            return self._record_log(gesture.value, "Next Slide / Move Right", "Executed")

        elif gesture == GestureType.SWIPE_LEFT:
            self._press_key("left")
            return self._record_log(gesture.value, "Previous Slide / Move Left", "Executed")

        elif gesture == GestureType.PINCH_OUT:
            self._hotkey("ctrl", "+")
            return self._record_log(gesture.value, "Zoom In (Ctrl + Plus)", "Executed")

        # Scrolling
        elif gesture == GestureType.POINTING_UP:
            self._scroll(self.config.scroll_amount)
            return self._record_log(gesture.value, "Scroll Up", "Executed")

        elif gesture == GestureType.POINTING_DOWN:
            self._scroll(-self.config.scroll_amount)
            return self._record_log(gesture.value, "Scroll Down", "Executed")

        return None

    def _press_key(self, key: str) -> bool:
        """Safely sends a single key press."""
        if self.action_executor is not None:
            ok = self.action_executor("press", key)
            if ok:
                self.total_actions_executed += 1
            return ok

        if pyautogui is None:
            return False
        try:
            pyautogui.press(key)
            self.total_actions_executed += 1
            return True
        except Exception as e:
            self._record_log("Error", f"Failed key press ({key}): {e}", "Error")
            return False

    def _hotkey(self, *keys: str) -> bool:
        """Safely sends a key combination."""
        combo = "+".join(keys)
        if self.action_executor is not None:
            ok = self.action_executor("hotkey", combo)
            if ok:
                self.total_actions_executed += 1
            return ok

        if pyautogui is None:
            return False
        try:
            pyautogui.hotkey(*keys)
            self.total_actions_executed += 1
            return True
        except Exception as e:
            self._record_log("Error", f"Failed hotkey ({combo}): {e}", "Error")
            return False

    def _scroll(self, amount: int) -> bool:
        """Safely scrolls the mouse wheel."""
        if self.action_executor is not None:
            ok = self.action_executor("scroll", str(amount))
            if ok:
                self.total_actions_executed += 1
            return ok

        if pyautogui is None:
            return False
        try:
            pyautogui.scroll(amount)
            self.total_actions_executed += 1
            return True
        except Exception as e:
            self._record_log("Error", f"Failed scroll: {e}", "Error")
            return False

    def _record_log(self, gesture: str, action: str, status: str) -> ActionLogEntry:
        """Logs an action entry and notifies listeners."""
        ts = time.strftime("%H:%M:%S")
        entry = ActionLogEntry(
            timestamp=ts,
            gesture=gesture,
            action=action,
            mode=self.current_mode.value,
            status=status
        )
        self.action_history.append(entry)
        self.last_action_desc = f"[{ts}] {gesture} -> {action}"

        if self.on_action_callback:
            try:
                self.on_action_callback(entry)
            except Exception:
                pass

        return entry
