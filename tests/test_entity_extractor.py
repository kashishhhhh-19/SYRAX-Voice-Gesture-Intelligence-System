"""
tests/test_entity_extractor.py - Unit tests for EntityExtractor
Verifies entity parsing for song titles, artists, app names, contacts, messages, and numeric parameters.
"""

import unittest
from core.entity_extractor import EntityExtractor


class TestEntityExtractor(unittest.TestCase):
    def setUp(self):
        self.extractor = EntityExtractor()

    def test_extract_song_title_and_artist(self):
        entities = self.extractor.extract("play Barsaat by Banjare")
        self.assertEqual(entities.song_title, "Barsaat")
        self.assertEqual(entities.artist, "Banjare")
        self.assertEqual(entities.app_name, "youtube")

    def test_extract_possessive_artist(self):
        entities = self.extractor.extract("play Arijit Singh's Tum Hi Ho")
        self.assertEqual(entities.artist, "Arijit Singh")
        self.assertEqual(entities.song_title, "Tum Hi Ho")

    def test_extract_whatsapp_contact_and_message(self):
        entities = self.extractor.extract("send a message to Rahul saying how are you")
        self.assertEqual(entities.contact_name, "Rahul")
        self.assertEqual(entities.message_content, "how are you")
        self.assertEqual(entities.app_name, "whatsapp")

    def test_extract_hinglish_whatsapp(self):
        entities = self.extractor.extract("Rahul ko message bhejo ki how are you")
        self.assertEqual(entities.contact_name, "Rahul")
        self.assertEqual(entities.message_content, "how are you")
        self.assertEqual(entities.app_name, "whatsapp")

    def test_extract_whatsapp_missing_message(self):
        entities = self.extractor.extract("send a whatsapp message to Rahul")
        self.assertEqual(entities.contact_name, "Rahul")
        self.assertIsNone(entities.message_content)

    def test_extract_search_query_and_target_app(self):
        entities = self.extractor.extract("search for relaxing music on YouTube")
        self.assertEqual(entities.query, "relaxing music")
        self.assertEqual(entities.app_name, "youtube")

    def test_extract_volume_amount(self):
        entities = self.extractor.extract("volume up by 20")
        self.assertEqual(entities.numeric_value, 20.0)
        self.assertEqual(entities.extra_params.get("amount"), 20)

    def test_app_alias_normalization(self):
        self.assertEqual(self.extractor.normalize_app_name("insta"), "instagram")
        self.assertEqual(self.extractor.normalize_app_name("yt"), "youtube")
        self.assertEqual(self.extractor.normalize_app_name("watsapp"), "whatsapp")
        self.assertEqual(self.extractor.normalize_app_name("my browser"), "browser")


if __name__ == "__main__":
    unittest.main()
