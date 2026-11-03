"""
tests/test_application_controller.py - Unit tests for ApplicationController
Validates window detection, context switching, and application-aware command routing.
"""

import unittest
from unittest.mock import MagicMock, patch
from core.application_controller import AppContext, ApplicationController


class TestApplicationController(unittest.TestCase):
    def setUp(self):
        self.mock_focus = MagicMock()
        self.mock_adapter = MagicMock()
        self.mock_focus._adapter = self.mock_adapter
        self.controller = ApplicationController(focus_manager=self.mock_focus)

    def test_detect_youtube_context(self):
        self.mock_adapter.get_foreground_window.return_value = 100
        self.mock_adapter.get_window_text.return_value = "Barsaat - Official Video - YouTube - Google Chrome"

        ctx = self.controller.detect_foreground_app()
        self.assertEqual(ctx, AppContext.YOUTUBE)

    def test_detect_instagram_context(self):
        self.mock_adapter.get_foreground_window.return_value = 200
        self.mock_adapter.get_window_text.return_value = "Instagram • Reels - Google Chrome"

        ctx = self.controller.detect_foreground_app()
        self.assertEqual(ctx, AppContext.INSTAGRAM)

    def test_detect_whatsapp_context(self):
        self.mock_adapter.get_foreground_window.return_value = 300
        self.mock_adapter.get_window_text.return_value = "(2) WhatsApp - Microsoft Edge"

        ctx = self.controller.detect_foreground_app()
        self.assertEqual(ctx, AppContext.WHATSAPP)

    @patch("actions.youtube_actions.YouTubeActions.next_video", return_value=(True, "Next YT Video"))
    def test_route_next_in_youtube_context(self, mock_yt_next):
        self.mock_adapter.get_foreground_window.return_value = 100
        self.mock_adapter.get_window_text.return_value = "YouTube - Google Chrome"

        success, msg, spoken = self.controller.route_context_action("next")
        self.assertTrue(success)
        mock_yt_next.assert_called_once()
        self.assertIn("Next video", spoken)

    @patch("actions.instagram_actions.InstagramActions.next_reel", return_value=(True, "Next Reel"))
    def test_route_next_in_instagram_context(self, mock_ig_next):
        self.mock_adapter.get_foreground_window.return_value = 200
        self.mock_adapter.get_window_text.return_value = "Instagram - Google Chrome"

        success, msg, spoken = self.controller.route_context_action("next")
        self.assertTrue(success)
        mock_ig_next.assert_called_once()
        self.assertIn("Next reel", spoken)


if __name__ == "__main__":
    unittest.main()
