"""
tests/test_command_parser.py - Unit Tests for SYRAX CommandParser
Validates regex rules, parameter extraction, fuzzy matching fallbacks,
and graceful degradation on unknown input.
"""

import unittest
from core.command_parser import CommandIntent, CommandParser


class TestCommandParser(unittest.TestCase):
    """Test suite for Natural Language Command Parser."""

    def setUp(self) -> None:
        self.parser = CommandParser()

    def test_greetings(self) -> None:
        """Test natural variations of greetings."""
        variations = ["Hello SYRAX", "hi", "hey syrax", "greetings", "good morning syrax"]
        for phrase in variations:
            cmd = self.parser.parse(phrase)
            self.assertEqual(cmd.intent, CommandIntent.GREETING, f"Failed for: {phrase}")
            self.assertEqual(cmd.confidence, 1.0)

    def test_open_sites(self) -> None:
        """Test browser opening commands for various target sites."""
        test_cases = [
            ("open youtube", "youtube"),
            ("launch google", "google"),
            ("go to github", "github"),
            ("open instagram", "instagram"),
            ("browse to reddit", "reddit"),
        ]
        for phrase, expected_target in test_cases:
            cmd = self.parser.parse(phrase)
            self.assertEqual(cmd.intent, CommandIntent.OPEN_SITE, f"Failed for: {phrase}")
            self.assertEqual(cmd.target, expected_target)
            self.assertEqual(cmd.action, "open")

    def test_search_queries(self) -> None:
        """Test Google web search commands and query parameter extraction."""
        test_cases = [
            ("search python programming tutorial", "python programming tutorial"),
            ("google machine learning algorithms", "machine learning algorithms"),
            ("find nearest coffee shop", "nearest coffee shop"),
            ("look up quantum computing basics", "quantum computing basics"),
        ]
        for phrase, expected_query in test_cases:
            cmd = self.parser.parse(phrase)
            self.assertEqual(cmd.intent, CommandIntent.SEARCH, f"Failed for: {phrase}")
            self.assertEqual(cmd.query, expected_query)

    def test_play_youtube_queries(self) -> None:
        """Test playing specific search queries on YouTube."""
        test_cases = [
            ("play python tutorial", "python tutorial"),
            ("play bohemian rhapsody", "bohemian rhapsody"),
            ("stream lofi hip hop beats", "lofi hip hop beats"),
            ("listen to mozart symphony 40", "mozart symphony 40"),
        ]
        for phrase, expected_query in test_cases:
            cmd = self.parser.parse(phrase)
            self.assertEqual(cmd.intent, CommandIntent.PLAY, f"Failed for: {phrase}")
            self.assertEqual(cmd.query, expected_query)

    def test_media_controls(self) -> None:
        """Test media playback controls (pause, resume, next, prev, forward, rewind)."""
        test_cases = [
            ("pause video", "pause"),
            ("pause", "pause"),
            ("stop music", "pause"),
            ("play music", "resume"),
            ("resume video", "resume"),
            ("next video", "next"),
            ("skip track", "next"),
            ("previous video", "previous"),
            ("fast forward", "forward"),
            ("forward 10 seconds", "forward"),
            ("rewind", "rewind"),
            ("go back", "rewind"),
        ]
        for phrase, expected_action in test_cases:
            cmd = self.parser.parse(phrase)
            self.assertEqual(cmd.intent, CommandIntent.MEDIA_CONTROL, f"Failed for: {phrase}")
            self.assertEqual(cmd.action, expected_action)

    def test_volume_controls(self) -> None:
        """Test master volume controls."""
        test_cases = [
            ("volume up", "volume_up"),
            ("turn it up", "volume_up"),
            ("louder", "volume_up"),
            ("volume down", "volume_down"),
            ("lower volume", "volume_down"),
            ("quieter", "volume_down"),
            ("mute", "mute"),
            ("unmute", "mute"),
        ]
        for phrase, expected_action in test_cases:
            cmd = self.parser.parse(phrase)
            self.assertEqual(cmd.intent, CommandIntent.VOLUME_CONTROL, f"Failed for: {phrase}")
            self.assertEqual(cmd.action, expected_action)

    def test_system_and_diagnostics(self) -> None:
        """Test exit and diagnostics triggers."""
        self.assertEqual(self.parser.parse("close assistant").intent, CommandIntent.EXIT)
        self.assertEqual(self.parser.parse("exit").intent, CommandIntent.EXIT)
        self.assertEqual(self.parser.parse("shutdown").intent, CommandIntent.EXIT)

        self.assertEqual(self.parser.parse("run diagnostics").intent, CommandIntent.DIAGNOSTICS)
        self.assertEqual(self.parser.parse("self test").intent, CommandIntent.DIAGNOSTICS)

    def test_gesture_mode_voice_commands(self) -> None:
        """Test voice commands toggling gesture mode ON and OFF."""
        start_phrases = [
            "start gesture mode",
            "activate gesture mode",
            "enable gesture mode",
            "turn on gesture mode",
            "gesture mode on",
        ]
        for phrase in start_phrases:
            cmd = self.parser.parse(phrase)
            self.assertEqual(cmd.intent, CommandIntent.GESTURE_MODE, f"Failed for: {phrase}")
            self.assertEqual(cmd.action, "start")

        stop_phrases = [
            "stop gesture mode",
            "deactivate gesture mode",
            "disable gesture mode",
            "turn off gesture mode",
            "exit gesture mode",
            "gesture mode off",
        ]
        for phrase in stop_phrases:
            cmd = self.parser.parse(phrase)
            self.assertEqual(cmd.intent, CommandIntent.GESTURE_MODE, f"Failed for: {phrase}")
            self.assertEqual(cmd.action, "stop")

    def test_fuzzy_matching_fallbacks(self) -> None:
        """Test handling of slight phonetic or transcription slips."""
        # 'paws video' -> 'pause video'
        cmd_pause = self.parser.parse("paws video")
        self.assertEqual(cmd_pause.intent, CommandIntent.MEDIA_CONTROL)
        self.assertEqual(cmd_pause.action, "pause")
        self.assertGreaterEqual(cmd_pause.confidence, 0.75)

        # 'open you tube' -> 'open youtube'
        cmd_yt = self.parser.parse("open you tube")
        self.assertEqual(cmd_yt.intent, CommandIntent.OPEN_SITE)
        self.assertEqual(cmd_yt.target, "youtube")

    def test_unknown_and_empty_inputs(self) -> None:
        """Test graceful handling of unknown text or empty queries."""
        empty_cmd = self.parser.parse("")
        self.assertEqual(empty_cmd.intent, CommandIntent.UNKNOWN)

        whitespace_cmd = self.parser.parse("   ")
        self.assertEqual(whitespace_cmd.intent, CommandIntent.UNKNOWN)

        random_cmd = self.parser.parse("flabbergasted extraterrestrial quantum pineapple")
        self.assertEqual(random_cmd.intent, CommandIntent.UNKNOWN)

    def test_phase1_required_utterances(self) -> None:
        """Verify the 11 Phase 1 benchmark utterances from Table 2.1."""
        # 1. 'SYRAX, play Barsaat by Banjare'
        c1 = self.parser.parse("SYRAX, play Barsaat by Banjare")
        self.assertEqual(c1.intent, CommandIntent.PLAY)
        self.assertEqual(c1.parameters.get("song_title"), "Barsaat")
        self.assertEqual(c1.parameters.get("artist"), "Banjare")

        # 2. 'Open Instagram and scroll reels'
        c2 = self.parser.parse("Open Instagram and scroll reels")
        self.assertEqual(c2.intent, CommandIntent.OPEN_SITE)
        self.assertEqual(c2.target, "instagram")
        self.assertIn("reels", c2.parameters.get("url", ""))

        # 3. 'Rahul ko message bhejo ki how are you'
        c3 = self.parser.parse("Rahul ko message bhejo ki how are you")
        self.assertEqual(c3.intent, CommandIntent.SEND_MESSAGE)
        self.assertEqual(c3.target, "Rahul")
        self.assertEqual(c3.query, "how are you")

        # 4. 'Send a WhatsApp message to Rahul'
        c4 = self.parser.parse("Send a WhatsApp message to Rahul")
        self.assertEqual(c4.intent, CommandIntent.SEND_MESSAGE)
        self.assertEqual(c4.target, "Rahul")
        self.assertIsNone(c4.query)

        # 6. 'SYRAX, stop' (interrupt, never exits)
        c6 = self.parser.parse("SYRAX, stop")
        self.assertEqual(c6.intent, CommandIntent.STOP)
        self.assertEqual(c6.action, "stop")

        # 7. 'Exit SYRAX'
        c7 = self.parser.parse("Exit SYRAX")
        self.assertEqual(c7.intent, CommandIntent.EXIT)

        # 8. 'SYRAX, volume up by 20'
        c8 = self.parser.parse("SYRAX, volume up by 20")
        self.assertEqual(c8.intent, CommandIntent.VOLUME_CONTROL)
        self.assertEqual(c8.parameters.get("amount"), 20)

        # 9. 'Search for relaxing music on YouTube'
        c9 = self.parser.parse("Search for relaxing music on YouTube")
        self.assertEqual(c9.intent, CommandIntent.SEARCH)
        self.assertEqual(c9.target, "youtube")
        self.assertEqual(c9.query, "relaxing music")

        # 10. 'Open my browser'
        c10 = self.parser.parse("Open my browser")
        self.assertEqual(c10.intent, CommandIntent.OPEN_SITE)
        self.assertEqual(c10.target, "browser")

        # 11. 'SYRAX' (wake word only)
        c11 = self.parser.parse("SYRAX")
        self.assertEqual(c11.intent, CommandIntent.GREETING)

    def test_multiturn_slot_filling_and_confirmation(self) -> None:
        """Test multi-turn slot resolution and spoken confirmation gating."""
        from core.conversation_state import ConversationState
        state = ConversationState()

        # Slot filling test: pending song slot
        state.set_pending_slot("song_title", "play_music", {})
        p_slot = CommandParser(conversation_state=state)
        cmd_song = p_slot.parse("Barsaat by Banjare")
        self.assertEqual(cmd_song.intent, CommandIntent.PLAY)
        self.assertEqual(cmd_song.parameters.get("song_title"), "Barsaat")
        self.assertEqual(cmd_song.parameters.get("artist"), "Banjare")

        # Confirmation test: 'haan bhejo'
        state.set_pending_confirmation("whatsapp_send", "Rahul", "how are you")
        p_conf = CommandParser(conversation_state=state)
        cmd_conf = p_conf.parse("haan bhejo")
        self.assertEqual(cmd_conf.intent, CommandIntent.CONFIRMATION)
        self.assertEqual(cmd_conf.action, "confirm")
        self.assertEqual(cmd_conf.parameters.get("recipient"), "Rahul")
        self.assertEqual(cmd_conf.parameters.get("content"), "how are you")

    def test_natural_language_and_close_commands(self) -> None:
        """Test Stage 2 natural phrasing, Devanagari Hindi, and specific close commands."""
        # 1. "Can you play Barsaat by Banjare?"
        c1 = self.parser.parse("Can you play Barsaat by Banjare?")
        self.assertEqual(c1.intent, CommandIntent.PLAY)
        self.assertEqual(c1.parameters.get("song_title"), "Barsaat")
        self.assertEqual(c1.parameters.get("artist"), "Banjare")

        # 2. "Let's watch a Python tutorial"
        c2 = self.parser.parse("Let's watch a Python tutorial")
        self.assertEqual(c2.intent, CommandIntent.PLAY)
        self.assertIn("Python tutorial", c2.query)

        # 3. "I want to listen to Arijit Singh"
        c3 = self.parser.parse("I want to listen to Arijit Singh")
        self.assertEqual(c3.intent, CommandIntent.PLAY)

        # 4. "Pause this for a moment"
        c4 = self.parser.parse("Pause this for a moment")
        self.assertEqual(c4.intent, CommandIntent.MEDIA_CONTROL)
        self.assertEqual(c4.action, "pause")

        # 5. "Play it again"
        c5 = self.parser.parse("Play it again")
        self.assertEqual(c5.intent, CommandIntent.MEDIA_CONTROL)
        self.assertEqual(c5.action, "resume")

        # 6. "Open Instagram and show me Reels"
        c6 = self.parser.parse("Open Instagram and show me Reels")
        self.assertEqual(c6.intent, CommandIntent.OPEN_SITE)
        self.assertEqual(c6.target, "instagram")

        # 7. "Find Rahul on WhatsApp and tell him I will call later"
        c7 = self.parser.parse("Find Rahul on WhatsApp and tell him I will call later")
        self.assertEqual(c7.intent, CommandIntent.SEND_MESSAGE)
        self.assertEqual(c7.target, "Rahul")
        self.assertEqual(c7.query, "I will call later")

        # 8. Close commands (Only EXIT closes SYRAX)
        c8a = self.parser.parse("Close YouTube")
        self.assertEqual(c8a.intent, CommandIntent.CLOSE_YOUTUBE)

        c8b = self.parser.parse("Close Instagram")
        self.assertEqual(c8b.intent, CommandIntent.CLOSE_INSTAGRAM)

        c8c = self.parser.parse("Close WhatsApp")
        self.assertEqual(c8c.intent, CommandIntent.CLOSE_WHATSAPP)

        c8d = self.parser.parse("Close this website")
        self.assertEqual(c8d.intent, CommandIntent.CLOSE_TAB)

        c8e = self.parser.parse("Close browser")
        self.assertEqual(c8e.intent, CommandIntent.CLOSE_BROWSER)

        # 9. Hindi Devanagari commands
        c9a = self.parser.parse("रुको")
        self.assertEqual(c9a.intent, CommandIntent.STOP)

        c9b = self.parser.parse("अलविदा")
        self.assertEqual(c9b.intent, CommandIntent.EXIT)

        c9c = self.parser.parse("यूट्यूब बंद करो")
        self.assertEqual(c9c.intent, CommandIntent.CLOSE_YOUTUBE)


if __name__ == "__main__":
    unittest.main()
