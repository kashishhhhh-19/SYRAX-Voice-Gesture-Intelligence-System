"""
actions/focus_manager.py - Browser Window Detection & Focus Manager for YouTube
Provides reliable detection, foreground window activation, safe-area click focusing,
focus caching, and serialized shortcut execution. Protects against executing keyboard
shortcuts when YouTube is not the verified active foreground window.
"""

import threading
import time
from typing import Callable, List, Optional, Protocol, Tuple

import config
from core.event_bus import Events, get_event_bus
from core.logger import get_logger

logger = get_logger("FocusManager")


class WindowAdapter(Protocol):
    """Protocol defining OS-level window and input operations for testability."""

    def enum_windows(self) -> List[int]: ...
    def get_window_text(self, hwnd: int) -> str: ...
    def is_window_visible(self, hwnd: int) -> bool: ...
    def is_iconic(self, hwnd: int) -> bool: ...
    def restore_window(self, hwnd: int) -> bool: ...
    def set_foreground_window(self, hwnd: int) -> bool: ...
    def get_foreground_window(self) -> int: ...
    def get_window_rect(self, hwnd: int) -> Tuple[int, int, int, int]: ...
    def click_at(self, x: int, y: int) -> None: ...
    def sleep(self, seconds: float) -> None: ...


class WindowsAPIAdapter:
    """Real Windows OS adapter using win32gui, win32con, and pyautogui."""

    def enum_windows(self) -> List[int]:
        hwnds: List[int] = []
        try:
            import win32gui
            def _cb(hwnd, extra):
                extra.append(hwnd)
            win32gui.EnumWindows(_cb, hwnds)
        except Exception as exc:
            logger.debug(f"win32gui.EnumWindows error: {exc}")
        return hwnds

    def get_window_text(self, hwnd: int) -> str:
        try:
            import win32gui
            return win32gui.GetWindowText(hwnd) or ""
        except Exception:
            return ""

    def is_window_visible(self, hwnd: int) -> bool:
        try:
            import win32gui
            return bool(win32gui.IsWindowVisible(hwnd))
        except Exception:
            return False

    def is_iconic(self, hwnd: int) -> bool:
        try:
            import win32gui
            return bool(win32gui.IsIconic(hwnd))
        except Exception:
            return False

    def restore_window(self, hwnd: int) -> bool:
        try:
            import win32gui
            import win32con
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            return True
        except Exception as exc:
            logger.debug(f"restore_window error: {exc}")
            return False

    def set_foreground_window(self, hwnd: int) -> bool:
        try:
            import win32gui
            import win32process
            import win32con
            import pyautogui

            if self.is_iconic(hwnd):
                self.restore_window(hwnd)

            # Standard Windows workaround: simulate an Alt key press to allow SetForegroundWindow
            try:
                pyautogui.press("alt")
            except Exception:
                pass

            win32gui.SetForegroundWindow(hwnd)
            return True
        except Exception as exc:
            logger.debug(f"set_foreground_window failed: {exc}")
            return False

    def get_foreground_window(self) -> int:
        try:
            import win32gui
            return int(win32gui.GetForegroundWindow())
        except Exception:
            return 0

    def get_window_rect(self, hwnd: int) -> Tuple[int, int, int, int]:
        try:
            import win32gui
            return win32gui.GetWindowRect(hwnd)
        except Exception:
            return (0, 0, 1280, 720)

    def click_at(self, x: int, y: int) -> None:
        try:
            import pyautogui
            pyautogui.click(x, y)
        except Exception as exc:
            logger.debug(f"click_at({x}, {y}) error: {exc}")

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


class FocusStatus:
    """Standardized dashboard focus status identifiers."""
    DETECTED = "YouTube Detected"
    FOCUSED = "YouTube Focused"
    SWITCHING = "Switching Focus"
    NOT_FOUND = "YouTube Not Found"


class FocusManager:
    """
    Manages browser window focus for YouTube automations.
    Ensures safe foreground activation, click-focusing, caching,
    and serializes action execution to prevent command interleaving.
    """

    def __init__(self, adapter: Optional[WindowAdapter] = None) -> None:
        self._adapter: WindowAdapter = adapter or WindowsAPIAdapter()
        self._event_bus = get_event_bus()

        self._lock = threading.RLock()
        self._execution_lock = threading.Lock()

        # Cache & state tracking
        self._last_focused_hwnd: Optional[int] = None
        self._last_focus_time: float = 0.0
        self._last_focus_attempt_time: float = 0.0
        self._last_not_found_speech_time: float = 0.0
        self._current_status: str = FocusStatus.NOT_FOUND

    def get_status(self) -> str:
        """Return the current YouTube focus status string."""
        with self._lock:
            return self._current_status

    def set_adapter(self, adapter: WindowAdapter) -> None:
        """Override OS adapter (used in unit tests)."""
        with self._lock:
            self._adapter = adapter

    def find_youtube_window(self) -> Optional[Tuple[int, str]]:
        """
        Enumerate open windows and find the active YouTube browser window.
        Ignores SYRAX dashboard windows.
        """
        try:
            hwnds = self._adapter.enum_windows()
            for hwnd in hwnds:
                if not self._adapter.is_window_visible(hwnd):
                    continue
                title = self._adapter.get_window_text(hwnd)
                if not title:
                    continue

                lower_title = title.lower()

                # Skip SYRAX dashboard
                if any(ign in lower_title for ign in config.APP_WINDOW_TITLE_IGNORE):
                    continue

                # Match YouTube keyword
                if any(kw in lower_title for kw in config.YOUTUBE_TITLE_KEYWORDS):
                    return (hwnd, title)
        except Exception as exc:
            logger.error(f"Error enumerating windows for YouTube: {exc}")
        return None

    def ensure_youtube_focused(self, needs_player_click: bool = True) -> Tuple[bool, str]:
        """
        Ensures YouTube is the active foreground window before shortcut execution.
        Applies focus caching, window restoration, foreground activation, and safe-area clicking.
        """
        with self._lock:
            now = time.time()

            # 1. Focus Cache Check:
            # If recently verified and still in foreground, skip expensive re-focus/click
            if (
                self._last_focused_hwnd is not None and
                (now - self._last_focus_time) < config.FOCUS_CACHE_SECONDS
            ):
                current_fg = self._adapter.get_foreground_window()
                if current_fg == self._last_focused_hwnd:
                    title = self._adapter.get_window_text(current_fg)
                    if any(kw in title.lower() for kw in config.YOUTUBE_TITLE_KEYWORDS):
                        return True, "YouTube Focused (Cached)"

            # 2. Rate limit consecutive focus switch attempts to prevent window flickering
            if (now - self._last_focus_attempt_time) < config.FOCUS_ATTEMPT_COOLDOWN_SECONDS:
                current_fg = self._adapter.get_foreground_window()
                if current_fg == self._last_focused_hwnd:
                    return True, "YouTube Focused (RateLimited)"
            self._last_focus_attempt_time = now

            # 3. Locate YouTube Window
            win_match = self.find_youtube_window()
            if not win_match:
                self._current_status = FocusStatus.NOT_FOUND
                self._event_bus.emit(
                    Events.YOUTUBE_FOCUS_CHANGED,
                    status=FocusStatus.NOT_FOUND,
                    message="YouTube window not open."
                )

                # Throttle spoken warning so it doesn't repeat continuously
                if (now - self._last_not_found_speech_time) >= config.YOUTUBE_NOT_FOUND_SPEECH_COOLDOWN:
                    self._last_not_found_speech_time = now
                    from core.event_bus import get_event_bus
                    get_event_bus().emit(
                        Events.ASSISTANT_RESPONSE,
                        text="Please open YouTube first.",
                        source="focus_manager"
                    )
                    get_event_bus().emit(
                        Events.ACTIVITY_LOG,
                        category="SYSTEM",
                        message="[FOCUS] YouTube Not Found. Action skipped."
                    )

                return False, "Please open YouTube first."

            hwnd, title = win_match
            self._current_status = FocusStatus.SWITCHING
            self._event_bus.emit(
                Events.YOUTUBE_FOCUS_CHANGED,
                status=FocusStatus.SWITCHING,
                message=f"Bringing '{title}' to foreground..."
            )

            # 4. Bring YouTube Window to Foreground with Retries
            focused_successfully = False
            for attempt in range(1, config.FOCUS_RETRY_COUNT + 1):
                if self._adapter.is_iconic(hwnd):
                    self._adapter.restore_window(hwnd)

                self._adapter.set_foreground_window(hwnd)
                self._adapter.sleep(config.FOCUS_DELAY_AFTER_FOREGROUND)

                if self._adapter.get_foreground_window() == hwnd:
                    focused_successfully = True
                    break
                logger.debug(f"Focus retry {attempt}/{config.FOCUS_RETRY_COUNT} for '{title}'")

            if not focused_successfully:
                fg_hwnd = self._adapter.get_foreground_window()
                fg_title = self._adapter.get_window_text(fg_hwnd)
                err_msg = f"Failed to foreground YouTube. Active window: '{fg_title}'"
                logger.warning(err_msg)
                self._current_status = FocusStatus.NOT_FOUND
                self._event_bus.emit(
                    Events.YOUTUBE_FOCUS_CHANGED,
                    status=FocusStatus.NOT_FOUND,
                    message=err_msg
                )
                return False, err_msg

            # 5. Safe Area / Player Area Click to Focus Tab Content
            if needs_player_click:
                rect = self._adapter.get_window_rect(hwnd)
                left, top, right, bottom = rect
                w = max(10, right - left)
                h = max(10, bottom - top)

                if config.CLICK_MODE == "player_center":
                    click_x = left + int(w * config.CLICK_PLAYER_CENTER_X_RATIO)
                    click_y = top + int(h * config.CLICK_PLAYER_CENTER_Y_RATIO)
                else:
                    # Default: "safe_area" below video player (prevents accidental pause/play)
                    click_x = left + int(w * config.CLICK_SAFE_AREA_X_RATIO)
                    click_y = top + int(h * config.CLICK_SAFE_AREA_Y_RATIO)

                logger.debug(f"Clicking neutral focus point ({click_x}, {click_y}) for '{title}'")
                self._adapter.click_at(click_x, click_y)
                self._adapter.sleep(config.FOCUS_DELAY_AFTER_CLICK)

            # 6. Re-verify Foreground Status Immediately Before Completion
            current_fg = self._adapter.get_foreground_window()
            if current_fg != hwnd:
                err_msg = "Foreground focus lost after clicking page."
                logger.warning(err_msg)
                return False, err_msg

            # 7. Update Cache & Status
            self._last_focused_hwnd = hwnd
            self._last_focus_time = time.time()
            self._current_status = FocusStatus.FOCUSED
            self._event_bus.emit(
                Events.YOUTUBE_FOCUS_CHANGED,
                status=FocusStatus.FOCUSED,
                message=f"YouTube Focused: '{title}'"
            )
            return True, "YouTube Focused"

    def execute_youtube_action(
        self,
        action_func: Callable[[], Tuple[bool, str]],
        needs_player_click: bool = True
    ) -> Tuple[bool, str]:
        """
        Executes a YouTube keyboard shortcut under an exclusive execution lock.
        Verifies and enforces browser foreground focus before and during shortcut transmission.
        """
        with self._execution_lock:
            # Step 1: Ensure focus
            success, msg = self.ensure_youtube_focused(needs_player_click=needs_player_click)
            if not success:
                logger.info(f"Skipping YouTube action: {msg}")
                return False, msg

            # Step 2: Re-check immediately before sending shortcut (Never send blind)
            current_fg = self._adapter.get_foreground_window()
            if current_fg != self._last_focused_hwnd:
                err = "Aborted: Foreground window changed right before shortcut execution."
                logger.error(err)
                return False, err

            # Step 3: Execute shortcut
            try:
                result = action_func()
                # Update focus timestamp on successful action
                self._last_focus_time = time.time()
                return result
            except Exception as exc:
                err = f"Error executing YouTube shortcut: {exc}"
                logger.error(err, exc_info=True)
                return False, err


# Global Singleton Instance
_global_focus_manager: Optional[FocusManager] = None
_fm_lock = threading.Lock()


def get_focus_manager() -> FocusManager:
    """Retrieve the global FocusManager singleton."""
    global _global_focus_manager
    with _fm_lock:
        if _global_focus_manager is None:
            _global_focus_manager = FocusManager()
        return _global_focus_manager
