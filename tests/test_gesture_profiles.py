"""
tests/test_gesture_profiles.py - Unit tests for Gesture Profiles
Validates YouTube, Instagram, and Presentation profile isolation and shortcut mapping.
"""

import unittest
from unittest.mock import MagicMock, patch
from gesture.gesture_actions import GestureActions
from gesture.gesture_profiles import InstagramGestureProfile, PresentationGestureProfile, YouTubeGestureProfile


class TestGestureProfiles(unittest.TestCase):
    def setUp(self):
        self.actions = GestureActions()

    @patch("actions.media_actions.MediaActions.toggle_play_pause", return_value=(True, "Paused"))
    def test_youtube_profile_open_palm(self, mock_play_pause):
        self.actions.set_profile(YouTubeGestureProfile())
        success, desc, spoken = self.actions.execute_gesture("OPEN_PALM_STEADY", "ACTIVE")
        self.assertTrue(success)
        self.assertEqual(desc, "Play / Pause")
        mock_play_pause.assert_called_once()

    @patch("actions.instagram_actions.InstagramActions.play_pause_reel", return_value=(True, "Reel Paused"))
    def test_instagram_profile_open_palm(self, mock_reel_pause):
        self.actions.set_profile(InstagramGestureProfile())
        success, desc, spoken = self.actions.execute_gesture("OPEN_PALM_STEADY", "ACTIVE")
        self.assertTrue(success)
        self.assertEqual(desc, "Reel Play/Pause")
        mock_reel_pause.assert_called_once()

    @patch("actions.instagram_actions.InstagramActions.next_reel", return_value=(True, "Next Reel"))
    def test_instagram_profile_one_finger_up_advances_reel(self, mock_next_reel):
        self.actions.set_profile(InstagramGestureProfile())
        success, desc, spoken = self.actions.execute_gesture("ONE_FINGER_UP", "ACTIVE")
        self.assertTrue(success)
        self.assertEqual(desc, "Next Reel")
        mock_next_reel.assert_called_once()

    @patch("actions.presentation_actions.PresentationActions.next_slide", return_value=(True, "Next Slide"))
    def test_presentation_profile_swipe_right(self, mock_slide):
        self.actions.set_profile(PresentationGestureProfile())
        success, desc, spoken = self.actions.execute_gesture("SWIPE_RIGHT", "ACTIVE")
        self.assertTrue(success)
        self.assertEqual(desc, "Next Slide")
        mock_slide.assert_called_once()

    def test_profile_switching_by_name(self):
        self.actions.set_profile_by_name("instagram")
        self.assertIsInstance(self.actions.get_active_profile(), InstagramGestureProfile)

        self.actions.set_profile_by_name("presentation")
        self.assertIsInstance(self.actions.get_active_profile(), PresentationGestureProfile)

        self.actions.set_profile_by_name("youtube")
        self.assertIsInstance(self.actions.get_active_profile(), YouTubeGestureProfile)


if __name__ == "__main__":
    unittest.main()
