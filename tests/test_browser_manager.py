"""
tests/test_browser_manager.py - Unit tests for BrowserManager CDP automation
Validates browser executable discovery, tab tracking safety, page ID isolation,
and JavaScript evaluation verification.
"""

import unittest
from unittest.mock import MagicMock, patch
from core.browser_manager import BrowserManager, BrowserActionResult


class TestBrowserManager(unittest.TestCase):
    def setUp(self):
        self.bm = BrowserManager(port=9999, profile_dir="tests/mock_profile")

    def test_initialization_sets_persistent_profile_and_port(self):
        self.assertEqual(self.bm.port, 9999)
        self.assertTrue(str(self.bm.profile_dir).endswith("mock_profile"))
        self.assertEqual(len(self.bm._syrax_page_ids), 0)

    def test_syrax_tab_isolation_never_closes_untracked_tab(self):
        """Strict safety test: BrowserManager must NEVER close a personal/untracked tab."""
        self.bm._context = MagicMock()
        mock_untracked_page = MagicMock()
        mock_untracked_page.url = "https://mail.google.com"
        mock_untracked_page.is_closed.return_value = False

        self.bm._context.pages = [mock_untracked_page]
        # Notice mock_untracked_page is NOT in self.bm._syrax_page_ids!

        with patch.object(self.bm, "is_connected", return_value=True):
            res = self.bm.close_tab()
            self.assertFalse(res.success)
            self.assertIn("No SYRAX-managed tab found", res.reason)
            mock_untracked_page.close.assert_not_called()

    def test_syrax_tab_closes_tracked_tab_only(self):
        """BrowserManager closes only pages registered in _syrax_page_ids."""
        self.bm._context = MagicMock()
        mock_page = MagicMock()
        mock_page.url = "https://www.youtube.com/watch?v=123"
        mock_page.is_closed.return_value = False

        page_id = self.bm._get_page_id(mock_page)
        self.bm._syrax_page_ids.add(page_id)
        self.bm._app_tabs["youtube"] = mock_page

        with patch.object(self.bm, "is_connected", return_value=True):
            res = self.bm.close_tab("youtube")
            self.assertTrue(res.success)
            mock_page.close.assert_called_once()
            self.assertNotIn(page_id, self.bm._syrax_page_ids)
            self.assertNotIn("youtube", self.bm._app_tabs)

    def test_evaluate_js_executes_and_verifies(self):
        mock_page = MagicMock()
        mock_page.is_closed.return_value = False
        mock_page.evaluate.return_value = {"paused": True, "currentTime": 42.5}
        self.bm._app_tabs["youtube"] = mock_page

        with patch.object(self.bm, "is_connected", return_value=True):
            res = self.bm.evaluate_js("youtube", "video.pause()")
            self.assertTrue(res.success)
            self.assertTrue(res.verified)
            self.assertEqual(res.data.get("currentTime"), 42.5)

    def test_evaluate_js_reports_unopened_tab_gracefully(self):
        with patch.object(self.bm, "is_connected", return_value=True):
            res = self.bm.evaluate_js("instagram", "window.scroll()")
            self.assertFalse(res.success)
            self.assertFalse(res.verified)
            self.assertIn("tab is not open", res.reason)


if __name__ == "__main__":
    unittest.main()
