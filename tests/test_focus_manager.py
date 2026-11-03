"""
tests/test_focus_manager.py - Unit Tests for YouTube FocusManager
Validates window detection, foregrounding, safe-area clicking, focus caching,
and error abort paths (YouTube Not Found, Wrong Foreground Window) using a mock OS adapter.
"""

import time
import unittest
from typing import Dict, List, Optional, Set, Tuple

import config
from actions.focus_manager import FocusManager, FocusStatus, WindowAdapter


class MockWindowOSAdapter:
    """Mock OS adapter recording all window and input calls for deterministic testing."""

    def __init__(self) -> None:
        self.windows: Dict[int, str] = {}
        self.visible_windows: Set[int] = set()
        self.minimized_windows: Set[int] = set()
        self.foreground_hwnd: int = 0
        self.rects: Dict[int, Tuple[int, int, int, int]] = {}
        self.click_log: List[Tuple[int, int]] = []
        self.call_log: List[str] = []
        self.allow_foreground_switch: bool = True

    def enum_windows(self) -> List[int]:
        self.call_log.append("enum_windows")
        return list(self.windows.keys())

    def get_window_text(self, hwnd: int) -> str:
        return self.windows.get(hwnd, "")

    def is_window_visible(self, hwnd: int) -> bool:
        return hwnd in self.visible_windows

    def is_iconic(self, hwnd: int) -> bool:
        return hwnd in self.minimized_windows

    def restore_window(self, hwnd: int) -> bool:
        self.call_log.append(f"restore_window({hwnd})")
        if hwnd in self.minimized_windows:
            self.minimized_windows.remove(hwnd)
        return True

    def set_foreground_window(self, hwnd: int) -> bool:
        self.call_log.append(f"set_foreground_window({hwnd})")
        if self.allow_foreground_switch:
            self.foreground_hwnd = hwnd
            return True
        return False

    def get_foreground_window(self) -> int:
        self.call_log.append("get_foreground_window")
        return self.foreground_hwnd

    def get_window_rect(self, hwnd: int) -> Tuple[int, int, int, int]:
        return self.rects.get(hwnd, (0, 0, 1000, 600))

    def click_at(self, x: int, y: int) -> None:
        self.call_log.append(f"click_at({x}, {y})")
        self.click_log.append((x, y))

    def sleep(self, seconds: float) -> None:
        # Avoid actual sleep delays in unit tests
        self.call_log.append(f"sleep({seconds})")


class TestFocusManager(unittest.TestCase):
    """Test suite for FocusManager."""

    def setUp(self) -> None:
        self.adapter = MockWindowOSAdapter()
        self.focus_mgr = FocusManager(adapter=self.adapter)
        # Ensure default click mode
        config.CLICK_MODE = "safe_area"

    def test_successful_detect_foreground_click_send_sequence(self) -> None:
        """Verify detect -> foreground -> click -> verify -> send sequence."""
        # Setup YouTube browser window and active Notepad window
        yt_hwnd = 101
        notepad_hwnd = 200

        self.adapter.windows[yt_hwnd] = "Python Tutorial - YouTube - Google Chrome"
        self.adapter.visible_windows.add(yt_hwnd)
        self.adapter.rects[yt_hwnd] = (100, 200, 1100, 800) # w=1000, h=600

        self.adapter.windows[notepad_hwnd] = "Untitled - Notepad"
        self.adapter.visible_windows.add(notepad_hwnd)
        self.adapter.foreground_hwnd = notepad_hwnd

        action_executed = False

        def mock_action() -> Tuple[bool, str]:
            nonlocal action_executed
            action_executed = True
            return True, "Shortcut sent"

        success, msg = self.focus_mgr.execute_youtube_action(mock_action, needs_player_click=True)

        self.assertTrue(success, f"Action failed: {msg}")
        self.assertTrue(action_executed, "Action function was not executed")
        self.assertEqual(self.adapter.foreground_hwnd, yt_hwnd)
        self.assertEqual(len(self.adapter.click_log), 1)

        # Check safe-area click coordinates
        # w=1000, h=600, left=100, top=200
        # click_x = 100 + int(1000 * 0.5) = 600
        # click_y = 200 + int(600 * 0.78) = 668
        expected_x = 100 + int(1000 * config.CLICK_SAFE_AREA_X_RATIO)
        expected_y = 200 + int(600 * config.CLICK_SAFE_AREA_Y_RATIO)
        self.assertEqual(self.adapter.click_log[0], (expected_x, expected_y))
        self.assertEqual(self.focus_mgr.get_status(), FocusStatus.FOCUSED)

    def test_youtube_not_found_aborts_action(self) -> None:
        """Verify action is skipped and reported when YouTube window is not open."""
        notepad_hwnd = 200
        self.adapter.windows[notepad_hwnd] = "Untitled - Notepad"
        self.adapter.visible_windows.add(notepad_hwnd)
        self.adapter.foreground_hwnd = notepad_hwnd

        action_called = False

        def mock_action() -> Tuple[bool, str]:
            nonlocal action_called
            action_called = True
            return True, "Executed"

        success, msg = self.focus_mgr.execute_youtube_action(mock_action)

        self.assertFalse(success)
        self.assertFalse(action_called, "Action must not execute when YouTube is not found")
        self.assertEqual(self.focus_mgr.get_status(), FocusStatus.NOT_FOUND)
        self.assertIn("Please open YouTube first", msg)

    def test_wrong_foreground_window_aborts_action(self) -> None:
        """Verify action is aborted if foreground switch fails to activate YouTube."""
        yt_hwnd = 101
        self.adapter.windows[yt_hwnd] = "Music - YouTube - Brave"
        self.adapter.visible_windows.add(yt_hwnd)
        self.adapter.foreground_hwnd = 300 # Some other window
        # Disallow foreground switch
        self.adapter.allow_foreground_switch = False

        action_called = False

        def mock_action() -> Tuple[bool, str]:
            nonlocal action_called
            action_called = True
            return True, "Executed"

        success, msg = self.focus_mgr.execute_youtube_action(mock_action)

        self.assertFalse(success)
        self.assertFalse(action_called, "Action must not execute if foreground verification fails")
        self.assertIn("Failed to foreground YouTube", msg)

    def test_focus_cache_skips_click(self) -> None:
        """Verify subsequent actions within cache interval skip the click step."""
        yt_hwnd = 101
        self.adapter.windows[yt_hwnd] = "YouTube - Google Chrome"
        self.adapter.visible_windows.add(yt_hwnd)
        self.adapter.foreground_hwnd = yt_hwnd

        # First call: clicks to focus
        success1, _ = self.focus_mgr.execute_youtube_action(lambda: (True, "1"), needs_player_click=True)
        self.assertTrue(success1)
        self.assertEqual(len(self.adapter.click_log), 1)

        # Second call immediately after: cached, does NOT click again
        success2, _ = self.focus_mgr.execute_youtube_action(lambda: (True, "2"), needs_player_click=True)
        self.assertTrue(success2)
        self.assertEqual(len(self.adapter.click_log), 1) # Still 1, no duplicate click

    def test_browser_level_action_skips_player_click(self) -> None:
        """Verify browser zoom and scroll actions (needs_player_click=False) never click player."""
        yt_hwnd = 101
        self.adapter.windows[yt_hwnd] = "YouTube - Mozilla Firefox"
        self.adapter.visible_windows.add(yt_hwnd)
        self.adapter.foreground_hwnd = yt_hwnd

        action_called = False

        def mock_scroll() -> Tuple[bool, str]:
            nonlocal action_called
            action_called = True
            return True, "Scrolled"

        success, _ = self.focus_mgr.execute_youtube_action(mock_scroll, needs_player_click=False)
        self.assertTrue(success)
        self.assertTrue(action_called)
        self.assertEqual(len(self.adapter.click_log), 0, "Browser action must not click the player")

    def test_restores_minimized_window(self) -> None:
        """Verify minimized YouTube window is restored via SW_RESTORE before foregrounding."""
        yt_hwnd = 101
        self.adapter.windows[yt_hwnd] = "YouTube - Microsoft Edge"
        self.adapter.visible_windows.add(yt_hwnd)
        self.adapter.minimized_windows.add(yt_hwnd)
        self.adapter.foreground_hwnd = 200

        success, _ = self.focus_mgr.execute_youtube_action(lambda: (True, "ok"))
        self.assertTrue(success)
        self.assertNotIn(yt_hwnd, self.adapter.minimized_windows)
        self.assertIn(f"restore_window({yt_hwnd})", self.adapter.call_log)

    def test_ignores_syrax_dashboard_window(self) -> None:
        """Verify SYRAX's own window is ignored during YouTube detection."""
        syrax_hwnd = 999
        self.adapter.windows[syrax_hwnd] = "SYRAX - Voice & Gesture Intelligence System (YouTube Mode)"
        self.adapter.visible_windows.add(syrax_hwnd)

        win = self.focus_mgr.find_youtube_window()
        self.assertIsNone(win, "SYRAX window must never be detected as the YouTube browser")


if __name__ == "__main__":
    unittest.main()
