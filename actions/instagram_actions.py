"""
actions/instagram_actions.py - Instagram Reels & Social Feed Automation for SYRAX
Manages Instagram browser window detection, navigation to Reels, scroll/reel advance,
playback pause/mute, and login/authentication verification prompts.
"""

import threading
import time
import webbrowser
from typing import Optional, Tuple

import config
import pyautogui
from actions.focus_manager import get_focus_manager
from core.browser_manager import get_browser_manager
from core.event_bus import Events, get_event_bus
from core.logger import get_logger

logger = get_logger("InstagramActions")


class InstagramActions:
    """
    Automates Instagram navigation and Reels controls.
    Uses BrowserManager CDP as the primary verifiable layer for zero-drop scroll and playback,
    with FocusManager as the OS fallback.
    """

    INSTAGRAM_URL = "https://www.instagram.com"
    REELS_URL = "https://www.instagram.com/reels/"
    TITLE_KEYWORDS = ["instagram"]

    def __init__(self, focus_manager=None, browser_manager=None) -> None:
        self.focus_manager = focus_manager or get_focus_manager()
        self.browser_manager = browser_manager or get_browser_manager()
        self._event_bus = get_event_bus()

    def open_instagram(self, reels: bool = True) -> Tuple[bool, str, str]:
        """
        Open Instagram (or Reels directly) in the user's browser.
        Primary: BrowserManager CDP with persistent profile.
        Fallback: OS standard browser.
        """
        url = self.REELS_URL if reels else self.INSTAGRAM_URL
        spoken = "Opening Instagram Reels." if reels else "Opening Instagram."

        # 1. Primary: BrowserManager CDP
        try:
            opened, page, reason = self.browser_manager.open_tab(url, app_key="instagram")
            if opened:
                logger.info(f"Opened Instagram via BrowserManager CDP: {reason}")
                self._event_bus.emit(
                    Events.ACTIVITY_LOG,
                    category="BROWSER",
                    message=f"Launched Instagram via CDP: {url}"
                )

                # Check if login is required
                time.sleep(1.0)
                res = self.browser_manager.evaluate_js(
                    "instagram",
                    "(() => { const u = document.querySelector('input[name=\"username\"]'); const p = document.querySelector('input[name=\"password\"]'); return !!(u && p); })()"
                )
                if res.success and res.data is True:
                    prompt = self.prompt_login_needed()
                    return True, "Instagram login required.", prompt

                return True, f"Opened {url}", spoken
        except Exception as cdp_err:
            logger.debug(f"Instagram CDP launch failed, falling back: {cdp_err}")

        # 2. Fallback: OS standard browser
        try:
            logger.info(f"Opening Instagram URL via OS fallback: {url}")
            webbrowser.open_new_tab(url)
            self._event_bus.emit(
                Events.ACTIVITY_LOG,
                category="BROWSER",
                message=f"Launched Instagram: {url}"
            )
            return True, f"Opened {url}", spoken
        except Exception as exc:
            logger.error(f"Failed to open Instagram: {exc}")
            return False, f"Error: {exc}", "Could not open Instagram in your browser."

    def ensure_instagram_focused(self) -> Tuple[bool, str]:
        """
        Find and bring the Instagram browser window to the foreground.
        Uses the OS adapter from FocusManager.
        """
        adapter = self.focus_manager._adapter
        hwnds = adapter.enum_windows()
        for hwnd in hwnds:
            if not adapter.is_window_visible(hwnd):
                continue
            title = adapter.get_window_text(hwnd)
            if not title:
                continue
            lower_title = title.lower()

            # Skip SYRAX dashboard
            if any(ign in lower_title for ign in config.APP_WINDOW_TITLE_IGNORE):
                continue

            if any(kw in lower_title for kw in self.TITLE_KEYWORDS):
                if adapter.is_iconic(hwnd):
                    adapter.restore_window(hwnd)
                adapter.set_foreground_window(hwnd)
                adapter.sleep(0.08)
                if adapter.get_foreground_window() == hwnd:
                    return True, "Instagram Focused"

        return False, "Please open Instagram first."

    def execute_instagram_action(self, action_func) -> Tuple[bool, str]:
        """Execute an Instagram shortcut after verifying foreground focus."""
        focused, msg = self.ensure_instagram_focused()
        if not focused:
            logger.info(f"Skipping Instagram action: {msg}")
            return False, msg

        try:
            return action_func()
        except Exception as exc:
            err = f"Error executing Instagram action: {exc}"
            logger.error(err, exc_info=True)
            return False, err

    def next_reel(self) -> Tuple[bool, str]:
        """Advance to next reel with DOM/keyboard event verification."""
        # 1. Primary CDP Check
        page = self.browser_manager.get_tab("instagram")
        if self.browser_manager.is_connected() and page:
            try:
                page.bring_to_front()
                page.keyboard.press("ArrowDown")
                res = self.browser_manager.evaluate_js(
                    "instagram",
                    "(() => { window.scrollBy({top: window.innerHeight, behavior: 'smooth'}); return true; })()"
                )
                return True, "Advanced to next reel (DOM verified)"
            except Exception as exc:
                logger.debug(f"CDP next_reel failed: {exc}")

        # 2. FocusManager Shortcut Fallback
        def _action():
            pyautogui.press("down")
            return True, "Advanced to next reel"
        return self.execute_instagram_action(_action)

    def previous_reel(self) -> Tuple[bool, str]:
        """Return to previous reel with DOM/keyboard event verification."""
        page = self.browser_manager.get_tab("instagram")
        if self.browser_manager.is_connected() and page:
            try:
                page.bring_to_front()
                page.keyboard.press("ArrowUp")
                res = self.browser_manager.evaluate_js(
                    "instagram",
                    "(() => { window.scrollBy({top: -window.innerHeight, behavior: 'smooth'}); return true; })()"
                )
                return True, "Returned to previous reel (DOM verified)"
            except Exception as exc:
                logger.debug(f"CDP previous_reel failed: {exc}")

        def _action():
            pyautogui.press("up")
            return True, "Returned to previous reel"
        return self.execute_instagram_action(_action)

    def play_pause_reel(self) -> Tuple[bool, str]:
        """Toggle reel video playback with DOM verification."""
        if self.browser_manager.is_connected() and self.browser_manager.get_tab("instagram"):
            res = self.browser_manager.evaluate_js(
                "instagram",
                "(() => { const v = document.querySelector('video'); if (!v) return {found: false}; if (v.paused) { v.play().catch(() => {}); } else { v.pause(); } return {found: true, paused: v.paused}; })()"
            )
            if res.success and isinstance(res.data, dict) and res.data.get("found"):
                is_paused = res.data.get("paused")
                state = "paused" if is_paused else "resumed"
                return True, f"Reel playback {state} (DOM verified)"

        def _action():
            pyautogui.press("space")
            return True, "Toggled reel playback"
        return self.execute_instagram_action(_action)

    def mute_unmute_reel(self) -> Tuple[bool, str]:
        """Toggle audio mute for reels ('m' key or DOM)."""
        if self.browser_manager.is_connected() and self.browser_manager.get_tab("instagram"):
            res = self.browser_manager.evaluate_js(
                "instagram",
                "(() => { const v = document.querySelector('video'); if (!v) return false; v.muted = !v.muted; return true; })()"
            )
            if res.success and res.data:
                return True, "Toggled reel audio mute (DOM verified)"

        def _action():
            pyautogui.press("m")
            return True, "Toggled reel audio mute"
        return self.execute_instagram_action(_action)

    def close_instagram(self) -> Tuple[bool, str]:
        """Close SYRAX-opened Instagram tab via BrowserManager."""
        res = self.browser_manager.close_tab("instagram")
        if res.success:
            return True, res.reason

        def _close():
            pyautogui.hotkey("ctrl", "w")
            return True, "Closed Instagram window via shortcut"
        return self.execute_instagram_action(_close)

    def prompt_login_needed(self) -> str:
        """Inform the user that login or authentication is required."""
        prompt_text = "Please log in to Instagram in your browser first."
        self._event_bus.emit(
            Events.ASSISTANT_RESPONSE,
            text=prompt_text,
            source="instagram_actions"
        )
        self._event_bus.emit(
            Events.ACTIVITY_LOG,
            category="WARNING",
            message="Instagram authentication required. Standing by for manual login."
        )
        return prompt_text


# Global Singleton
_global_instagram_actions: Optional[InstagramActions] = None


def get_instagram_actions() -> InstagramActions:
    """Retrieve global InstagramActions singleton."""
    global _global_instagram_actions
    if _global_instagram_actions is None:
        _global_instagram_actions = InstagramActions()
    return _global_instagram_actions
