"""
tests/test_youtube_actions.py - Unit tests for YouTubeActions and Candidate Scoring
Validates song/artist ranking heuristics, cancellation handling, and playback launch logic.
"""

import threading
import unittest
from unittest.mock import MagicMock, patch
from actions.youtube_actions import YouTubeActions, YouTubeCandidate, score_candidate


class TestYouTubeActions(unittest.TestCase):
    def setUp(self):
        self.mock_focus = MagicMock()
        self.mock_bm = MagicMock()
        self.mock_bm.is_connected.return_value = False
        self.mock_bm.open_tab.return_value = (False, None, "CDP disabled in mock test")
        self.yt = YouTubeActions(focus_manager=self.mock_focus, browser_manager=self.mock_bm)

    def test_score_candidate_exact_match_official(self):
        cand1 = YouTubeCandidate(
            video_id="abc12345678",
            title="Barsaat - Official Music Video | Banjare",
            channel="Banjare Records",
            is_official=True
        )
        cand2 = YouTubeCandidate(
            video_id="def12345678",
            title="Barsaat (1 Hour Loop)",
            channel="Random Looper",
            is_official=False
        )

        score1 = score_candidate(cand1, song_title="Barsaat", artist="Banjare")
        score2 = score_candidate(cand2, song_title="Barsaat", artist="Banjare")

        self.assertGreater(score1, score2)
        self.assertGreater(score1, 60.0)
        self.assertLess(score2, score1)

    def test_score_candidate_penalizes_loops_and_reverb(self):
        cand = YouTubeCandidate(
            video_id="xyz12345678",
            title="Barsaat - Banjare (Slowed + Reverb 10 Hours)",
            channel="Chill Mixes",
            is_official=False
        )
        score = score_candidate(cand, song_title="Barsaat", artist="Banjare")
        # Penalties for "10 hours", "slowed", "reverb"
        self.assertLess(score, 40.0)

    @patch("webbrowser.open_new_tab")
    def test_play_best_match_selects_winner(self, mock_browser):
        candidates = [
            YouTubeCandidate("vid1", "Random Cover Barsaat", "CoverArtist"),
            YouTubeCandidate("vid2", "Barsaat | Banjare Official Audio", "Banjare Official", is_official=True)
        ]
        self.yt.search_candidates = MagicMock(return_value=candidates)

        success, msg, speech = self.yt.play_best_match(
            query="Barsaat by Banjare",
            song_title="Barsaat",
            artist="Banjare",
            wait_time=0.0
        )

        self.assertTrue(success)
        mock_browser.assert_called_with("https://www.youtube.com/watch?v=vid2")
        self.assertIn("Barsaat", speech)
        self.assertIn("Banjare", speech)

    @patch("webbrowser.open_new_tab")
    def test_play_best_match_cancellation(self, mock_browser):
        token = threading.Event()
        token.set()  # Already cancelled

        success, msg, speech = self.yt.play_best_match(
            query="Barsaat by Banjare",
            cancellation_token=token
        )

        self.assertFalse(success)
        self.assertEqual(msg, "Cancelled")
        mock_browser.assert_not_called()

    @patch("webbrowser.open_new_tab")
    def test_play_best_match_fallback_when_no_candidates(self, mock_browser):
        self.yt.search_candidates = MagicMock(return_value=[])

        success, msg, speech = self.yt.play_best_match(
            query="Barsaat by Banjare",
            song_title="Barsaat",
            artist="Banjare",
            wait_time=0.0
        )

        self.assertTrue(success)
        mock_browser.assert_called_with("https://www.youtube.com/results?search_query=Barsaat+Banjare")
        self.assertIn("Barsaat", speech)

    def test_play_pause_cdp_verification(self):
        from core.browser_manager import BrowserActionResult
        self.mock_bm.is_connected.return_value = True
        self.mock_bm.get_tab.return_value = MagicMock()
        self.mock_bm.evaluate_js.return_value = BrowserActionResult(
            success=True,
            verified=True,
            reason="ok",
            data={"found": True, "paused": True}
        )

        success, msg = self.yt.play_pause()
        self.assertTrue(success)
        self.assertIn("DOM verified", msg)

    def test_close_youtube(self):
        from core.browser_manager import BrowserActionResult
        self.mock_bm.close_tab.return_value = BrowserActionResult(
            success=True,
            verified=True,
            reason="Closed youtube tab."
        )

        success, msg = self.yt.close_youtube()
        self.assertTrue(success)
        self.mock_bm.close_tab.assert_called_with("youtube")


if __name__ == "__main__":
    unittest.main()
