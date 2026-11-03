"""
tests/test_interrupt_manager.py - Unit tests for InterruptManager
Verifies interrupt keyword detection, cancellation token behavior, and TTS purge invocation.
"""

import unittest
from unittest.mock import MagicMock
from core.interrupt_manager import InterruptManager, InterruptType


class TestInterruptManager(unittest.TestCase):
    def setUp(self):
        self.mock_tts = MagicMock()
        self.manager = InterruptManager(tts_engine=self.mock_tts)

    def test_detect_stop_activity(self):
        stops = ["stop", "ruko", "cancel", "band karo", "freeze", "halt"]
        for word in stops:
            itype = self.manager.check_for_interrupt_phrase(word)
            self.assertEqual(itype, InterruptType.STOP_ACTIVITY, f"Failed for {word}")

    def test_detect_exit_syrax(self):
        exits = ["exit syrax", "close syrax", "quit syrax"]
        for phrase in exits:
            itype = self.manager.check_for_interrupt_phrase(phrase)
            self.assertEqual(itype, InterruptType.EXIT_SYRAX, f"Failed for {phrase}")

    def test_detect_pause(self):
        pauses = ["pause", "hold video"]
        for p in pauses:
            itype = self.manager.check_for_interrupt_phrase(p)
            self.assertEqual(itype, InterruptType.PAUSE, f"Failed for {p}")

    def test_interrupt_triggers_tts_purge_and_sets_event(self):
        self.assertFalse(self.manager.is_interrupted())
        self.manager.trigger_interrupt(reason="User said stop")
        self.assertTrue(self.manager.is_interrupted())
        self.mock_tts.purge.assert_called_once()

    def test_clear_interrupt_resets_token(self):
        self.manager.trigger_interrupt()
        self.assertTrue(self.manager.is_interrupted())
        self.manager.clear_interrupt()
        self.assertFalse(self.manager.is_interrupted())


if __name__ == "__main__":
    unittest.main()
