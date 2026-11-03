"""
tests/test_intent_classifier.py - Unit tests for IntentClassifier
Verifies English, Hindi, and Hinglish intent classification across all supported intents.
"""

import unittest
from core.intent_classifier import IntentClassifier, IntentType


class TestIntentClassifier(unittest.TestCase):
    def setUp(self):
        self.classifier = IntentClassifier()

    def test_interrupt_stop_classification(self):
        phrases = ["stop", "cancel", "ruko", "roko", "band karo", "halt", "freeze"]
        for p in phrases:
            intent, conf, _ = self.classifier.classify(p)
            self.assertEqual(intent, IntentType.INTERRUPT_STOP, f"Failed for {p}")
            self.assertGreaterEqual(conf, 0.9)

    def test_exit_classification(self):
        phrases = ["exit syrax", "close syrax", "quit syrax", "shut down syrax", "alvida"]
        for p in phrases:
            intent, conf, _ = self.classifier.classify(p)
            self.assertEqual(intent, IntentType.EXIT_APP, f"Failed for {p}")
            self.assertEqual(conf, 1.0)

    def test_play_music_classification(self):
        phrases = [
            "play Barsaat by Banjare",
            "play some music",
            "stream bohemian rhapsody",
            "gaana chalao",
            "Arijit Singh ka song bajao"
        ]
        for p in phrases:
            intent, conf, _ = self.classifier.classify(p)
            self.assertEqual(intent, IntentType.PLAY_MUSIC, f"Failed for {p}")

    def test_send_message_classification(self):
        phrases = [
            "send a whatsapp message to Rahul",
            "Rahul ko message bhejo ki how are you",
            "send message to Priya",
            "whatsapp karo Kashish ko"
        ]
        for p in phrases:
            intent, conf, _ = self.classifier.classify(p)
            self.assertEqual(intent, IntentType.SEND_MESSAGE, f"Failed for {p}")

    def test_scroll_feed_classification(self):
        phrases = [
            "scroll reels",
            "next reel",
            "previous reel",
            "reel badlo",
            "agla reel"
        ]
        for p in phrases:
            intent, conf, _ = self.classifier.classify(p)
            self.assertEqual(intent, IntentType.SCROLL_FEED, f"Failed for {p}")

    def test_volume_controls_classification(self):
        phrases = ["volume up", "awaaz badhao", "louder", "volume down", "awaaz kam", "mute", "chup ho jao"]
        for p in phrases:
            intent, conf, _ = self.classifier.classify(p)
            self.assertEqual(intent, IntentType.VOLUME_CONTROL, f"Failed for {p}")

    def test_language_detection(self):
        self.assertEqual(self.classifier.detect_language("play music"), "english")
        self.assertEqual(self.classifier.detect_language("Rahul ko message bhejo"), "hinglish")
        self.assertEqual(self.classifier.detect_language("awaaz kam karo"), "hinglish")


if __name__ == "__main__":
    unittest.main()
