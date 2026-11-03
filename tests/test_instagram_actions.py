"""
tests/test_instagram_actions.py - Unit tests for InstagramActions
Validates Instagram navigation, window focus, keyboard shortcut dispatch, and login prompt detection.
"""

import unittest
from unittest.mock import MagicMock, patch
from actions.instagram_actions import InstagramActions


class TestInstagramActions(unittest.TestCase):
    def setUp(self):
        self.mock_focus = MagicMock()
        self.mock_adapter = MagicMock()
        self.mock_focus._adapter = self.mock_adapter
        self.mock_bm = MagicMock()
        self.mock_bm.is_connected.return_value = False
        self.mock_bm.get_tab.return_value = None
        self.mock_bm.open_tab.return_value = (False, None, "CDP disabled in mock test")
        self.ig = InstagramActions(focus_manager=self.mock_focus, browser_manager=self.mock_bm)

    @patch("webbrowser.open_new_tab")
    def test_open_instagram_reels(self, mock_browser):
        success, msg, speech = self.ig.open_instagram(reels=True)
        self.assertTrue(success)
        mock_browser.assert_called_with("https://www.instagram.com/reels/")
        self.assertIn("Reels", speech)

    @patch("pyautogui.press")
    def test_next_reel_dispatches_down_key_when_focused(self, mock_press):
        # Configure adapter to report Instagram window is open and focused
        self.mock_adapter.enum_windows.return_value = [1001]
        self.mock_adapter.is_window_visible.return_value = True
        self.mock_adapter.get_window_text.return_value = "Instagram • Photos and Videos - Google Chrome"
        self.mock_adapter.is_iconic.return_value = False
        self.mock_adapter.get_foreground_window.return_value = 1001

        success, msg = self.ig.next_reel()
        self.assertTrue(success)
        mock_press.assert_called_with("down")

    @patch("pyautogui.press")
    def test_play_pause_reel_dispatches_space_key(self, mock_press):
        self.mock_adapter.enum_windows.return_value = [1001]
        self.mock_adapter.is_window_visible.return_value = True
        self.mock_adapter.get_window_text.return_value = "Instagram - Google Chrome"
        self.mock_adapter.is_iconic.return_value = False
        self.mock_adapter.get_foreground_window.return_value = 1001

        success, msg = self.ig.play_pause_reel()
        self.assertTrue(success)
        mock_press.assert_called_with("space")

    def test_action_skipped_when_instagram_not_open(self):
        self.mock_adapter.enum_windows.return_value = [2001]
        self.mock_adapter.is_window_visible.return_value = True
        self.mock_adapter.get_window_text.return_value = "Notepad - Untitled"

        success, msg = self.ig.next_reel()
        self.assertFalse(success)
        self.assertIn("Please open Instagram first", msg)

    def test_login_prompt_generates_spoken_and_event(self):
        prompt = self.ig.prompt_login_needed()
        self.assertIn("log in to Instagram", prompt)

    def test_next_reel_cdp_verification(self):
        from core.browser_manager import BrowserActionResult
        mock_page = MagicMock()
        self.mock_bm.is_connected.return_value = True
        self.mock_bm.get_tab.return_value = mock_page
        self.mock_bm.evaluate_js.return_value = BrowserActionResult(
            success=True,
            verified=True,
            reason="scrolled",
            data=True
        )

        success, msg = self.ig.next_reel()
        self.assertTrue(success)
        self.assertIn("DOM verified", msg)
        mock_page.keyboard.press.assert_called_with("ArrowDown")

    def test_close_instagram(self):
        from core.browser_manager import BrowserActionResult
        self.mock_bm.close_tab.return_value = BrowserActionResult(
            success=True,
            verified=True,
            reason="Closed instagram tab."
        )

        success, msg = self.ig.close_instagram()
        self.assertTrue(success)
        self.mock_bm.close_tab.assert_called_with("instagram")


if __name__ == "__main__":
    unittest.main()
