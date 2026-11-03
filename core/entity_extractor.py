"""
core/entity_extractor.py - Natural Language Entity Extractor for SYRAX
Extracts song titles, artists, app names, contact names, message text, and numeric values
with alias normalization and multilingual regex/pattern rules.
"""

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class ExtractedEntities:
    """Structured container for entities parsed from natural voice commands."""
    song_title: Optional[str] = None
    artist: Optional[str] = None
    app_name: Optional[str] = None
    contact_name: Optional[str] = None
    message_content: Optional[str] = None
    query: Optional[str] = None
    action: Optional[str] = None
    numeric_value: Optional[float] = None
    extra_params: Dict[str, Any] = field(default_factory=dict)


def _clean_val(v: Optional[str]) -> Optional[str]:
    """Strip whitespace and punctuation artifacts from entity strings."""
    if not v:
        return None
    cleaned = v.strip(" \t\r\n?.!,;:\'\"")
    return cleaned if cleaned else None


class EntityExtractor:
    """
    Extracts semantic entities from user input across English, Hindi, and Hinglish.
    Normalizes app aliases (e.g. 'insta' -> 'instagram', 'yutube' -> 'youtube').
    """

    APP_ALIASES = {
        "insta": "instagram",
        "ig": "instagram",
        "instagram": "instagram",
        "whatsapp": "whatsapp",
        "whats app": "whatsapp",
        "what's app": "whatsapp",
        "watsapp": "whatsapp",
        "watsup": "whatsapp",
        "youtube": "youtube",
        "you tube": "youtube",
        "yt": "youtube",
        "yutube": "youtube",
        "google": "google",
        "chrome": "chrome",
        "github": "github",
        "spotify": "spotify",
        "browser": "browser",
        "my browser": "browser",
        "web browser": "browser",
        "the browser": "browser",
    }

    def __init__(self) -> None:
        self._compile_patterns()

    def _compile_patterns(self) -> None:
        """Compile regexes for entity extraction."""
        # 1. "Play [song] by [artist]" / "Can you play [song] by [artist]" / "Let's watch [video]"
        self._re_play_by = re.compile(
            r"\b(?:can\s+you\s+play|please\s+play|play)\s+(?:the\s+)?(.+?)\s+(?:song\s+)?by\s+(.+?)(?:\s+on\s+youtube)?$",
            re.IGNORECASE
        )
        self._re_artist_possessive = re.compile(
            r"\b(?:can\s+you\s+play|please\s+play|play)\s+(.+?)'s\s+(.+)$",
            re.IGNORECASE
        )
        self._re_play_generic = re.compile(
            r"\b(?:play|stream|listen\s+to|let'?s\s+watch|i\s+want\s+to\s+listen\s+to|can\s+you\s+play|please\s+play|chalao|bajao|sunao)\s+(?:a\s+|the\s+)?(.+?)(?:\s+on\s+youtube)?$",
            re.IGNORECASE
        )
        self._re_hinglish_play = re.compile(
            r"(.+?)\s+ka\s+(.+?)(?:\s+gaana|\s+song)?\s+(?:chalao|bajao|sunao)$",
            re.IGNORECASE
        )

        # 2. Search on App: "Search for relaxing music on YouTube"
        self._re_search_on_app = re.compile(
            r"\b(?:search\s+for|search|look\s+up|find)\s+(.+?)\s+on\s+([a-zA-Z0-9_\s]+)$",
            re.IGNORECASE
        )
        self._re_search_generic = re.compile(
            r"\b(?:search\s+for|search|google\s+for|google|look\s+up|find)\s+(.+)$",
            re.IGNORECASE
        )

        # 3. WhatsApp Messaging:
        # "Find Rahul on WhatsApp and tell him I will call later"
        self._re_find_and_tell = re.compile(
            r"\bfind\s+([a-zA-Z0-9_]+)\s+on\s+whatsapp\s+and\s+tell\s+(?:him|her|them)?\s*(.+)$",
            re.IGNORECASE
        )
        # "Send a message to Rahul saying how are you"
        # "Send Rahul a WhatsApp message saying how are you"
        self._re_msg_english_to = re.compile(
            r"\bsend\s+(?:a\s+)?(?:whatsapp\s+)?message\s+to\s+([a-zA-Z0-9_]+)(?:\s+(?:saying|that|with\s+text)\s+(.+))?$",
            re.IGNORECASE
        )
        self._re_msg_english_direct = re.compile(
            r"\bsend\s+([a-zA-Z0-9_]+)\s+(?:a\s+)?(?:whatsapp\s+)?message(?:\s+(?:saying|that|with\s+text)\s+(.+))?$",
            re.IGNORECASE
        )
        self._re_msg_hinglish = re.compile(
            r"([a-zA-Z0-9_]+)\s+ko\s+(?:whatsapp\s+)?message\s+bhejo(?:\s+(?:ki|saying)\s+(.+))?$",
            re.IGNORECASE
        )
        self._re_find_contact = re.compile(
            r"\b(?:find|open)\s+([a-zA-Z0-9_]+)(?:'s)?(?:\s+chat)?\s+on\s+whatsapp\b|\bfind\s+([a-zA-Z0-9_]+)\s+on\s+whatsapp\b",
            re.IGNORECASE
        )

        # 4. Open App: "Open Instagram", "Open WhatsApp", "Go to YouTube"
        self._re_open_app = re.compile(
            r"\b(?:open|launch|start|go\s+to|kholo)\s+([a-zA-Z0-9_\s]+)",
            re.IGNORECASE
        )

        # 5. Numeric seconds, percentages, volume amounts
        self._re_seconds = re.compile(r"\b(\d+)\s*(?:seconds?|s|secs?)\b", re.IGNORECASE)
        self._re_percent = re.compile(r"\b(\d+)\s*%", re.IGNORECASE)
        self._re_volume_amount = re.compile(r"\b(?:by|to|level)?\s*(\d{1,3})\s*(?:%|percent)?\b", re.IGNORECASE)

    def normalize_app_name(self, raw_app: str) -> str:
        """Map aliases like 'insta' -> 'instagram', 'yt' -> 'youtube'."""
        clean = raw_app.strip().lower()
        return self.APP_ALIASES.get(clean, clean)

    def extract(self, text: str, intent_hint: Optional[str] = None) -> ExtractedEntities:
        """
        Extract semantic entities from text, taking into account intent hints if available.
        """
        entities = ExtractedEntities()
        clean = _clean_val(text) or ""
        if not clean:
            return entities

        # 1. Extract numeric values (seconds, percentages)
        sec_match = self._re_seconds.search(clean)
        if sec_match:
            entities.numeric_value = float(sec_match.group(1))
            entities.extra_params["seconds"] = int(sec_match.group(1))

        pct_match = self._re_percent.search(clean)
        if pct_match:
            entities.numeric_value = float(pct_match.group(1))
            entities.extra_params["percent"] = int(pct_match.group(1))

        # Volume amount (e.g., "volume up by 20", "set volume to 50", "turn it up 15")
        if any(w in clean.lower() for w in ("volume", "vol", "awaaz", "louder", "quieter")):
            vol_match = re.search(r"\b(?:by|to)?\s*(\d{1,3})\b", clean, re.IGNORECASE)
            if vol_match and not sec_match and not pct_match:
                val = int(vol_match.group(1))
                if 0 <= val <= 100:
                    entities.numeric_value = float(val)
                    entities.extra_params["amount"] = val

        # 2. Extract WhatsApp Messaging Entities
        m_fat = self._re_find_and_tell.search(clean)
        if m_fat:
            entities.app_name = "whatsapp"
            cname = _clean_val(m_fat.group(1))
            entities.contact_name = cname.capitalize() if cname else None
            entities.message_content = _clean_val(m_fat.group(2))
            return entities

        m_eng_to = self._re_msg_english_to.search(clean)
        if m_eng_to:
            entities.app_name = "whatsapp"
            cname = _clean_val(m_eng_to.group(1))
            entities.contact_name = cname.capitalize() if cname else None
            entities.message_content = _clean_val(m_eng_to.group(2))
            return entities

        m_eng_dir = self._re_msg_english_direct.search(clean)
        if m_eng_dir:
            entities.app_name = "whatsapp"
            cname = _clean_val(m_eng_dir.group(1))
            entities.contact_name = cname.capitalize() if cname else None
            entities.message_content = _clean_val(m_eng_dir.group(2))
            return entities

        m_hin = self._re_msg_hinglish.search(clean)
        if m_hin:
            entities.app_name = "whatsapp"
            cname = _clean_val(m_hin.group(1))
            entities.contact_name = cname.capitalize() if cname else None
            entities.message_content = _clean_val(m_hin.group(2))
            return entities

        m_find = self._re_find_contact.search(clean)
        if m_find:
            entities.app_name = "whatsapp"
            cname = _clean_val(m_find.group(1) or m_find.group(2))
            if cname:
                entities.contact_name = cname.capitalize()
            return entities

        # 3. Extract Search on App: "Search for relaxing music on YouTube"
        m_s_app = self._re_search_on_app.search(clean)
        if m_s_app:
            entities.query = _clean_val(m_s_app.group(1))
            entities.app_name = self.normalize_app_name(m_s_app.group(2).strip())
            return entities

        # 4. Extract Music Playback Entities:
        # "Play Barsaat song by Banjare" -> song_title="Barsaat", artist="Banjare"
        m_play_by = self._re_play_by.search(clean)
        if m_play_by:
            entities.song_title = _clean_val(m_play_by.group(1))
            entities.artist = _clean_val(m_play_by.group(2))
            entities.query = f"{entities.song_title} by {entities.artist}"
            entities.app_name = "youtube"
            return entities

        # "Play Arijit Singh's latest songs" -> artist="Arijit Singh", song_title="latest songs"
        m_poss = self._re_artist_possessive.search(clean)
        if m_poss:
            entities.artist = _clean_val(m_poss.group(1))
            entities.song_title = _clean_val(m_poss.group(2))
            entities.query = f"{entities.artist} {entities.song_title}"
            entities.app_name = "youtube"
            return entities

        # Hinglish: "Arijit Singh ka Barsaat gaana chalao"
        m_h_play = self._re_hinglish_play.search(clean)
        if m_h_play:
            entities.artist = _clean_val(m_h_play.group(1))
            entities.song_title = _clean_val(m_h_play.group(2))
            entities.query = f"{entities.song_title} {entities.artist}"
            entities.app_name = "youtube"
            return entities
            entities.app_name = "youtube"
            return entities

        # Generic Play: "Play some music" or "Play Barsaat"
        if intent_hint == "play_music" or clean.lower().startswith("play "):
            m_p_gen = self._re_play_generic.search(clean)
            if m_p_gen:
                q = m_p_gen.group(1).strip()
                # Check if query is just generic placeholder like "some music" or "music"
                if q.lower() in ("some music", "music", "a song", "songs", "gaana"):
                    entities.song_title = None
                    entities.artist = None
                    entities.query = ""
                    entities.extra_params["needs_slot"] = True
                else:
                    entities.query = q
                    entities.song_title = q
                entities.app_name = "youtube"
                return entities

        # 5. Extract Search Query
        m_search = self._re_search_generic.search(clean)
        if m_search:
            entities.query = m_search.group(1).strip()
            return entities

        # 6. Extract Open App / Site Target
        if "instagram" in clean.lower() and "reel" in clean.lower():
            entities.app_name = "instagram"
            entities.action = "scroll_reels"
            entities.extra_params["mode"] = "reels"
            return entities

        m_open = self._re_open_app.search(clean)
        if m_open:
            app = self.normalize_app_name(m_open.group(1).strip())
            entities.app_name = app
            return entities

        # 7. Media Control Action extraction
        clean_lower = clean.lower()
        if "pause" in clean_lower or "roko" in clean_lower:
            entities.action = "pause"
        elif "resume" in clean_lower or "unpause" in clean_lower or "chalu" in clean_lower:
            entities.action = "resume"
        elif "next" in clean_lower or "skip" in clean_lower or "agla" in clean_lower:
            entities.action = "next"
        elif "prev" in clean_lower or "previous" in clean_lower or "pichla" in clean_lower:
            entities.action = "previous"
        elif "forward" in clean_lower or "aage" in clean_lower:
            entities.action = "forward"
        elif "rewind" in clean_lower or "piche" in clean_lower:
            entities.action = "rewind"
        elif "volume up" in clean_lower or "awaaz badhao" in clean_lower or "louder" in clean_lower:
            entities.action = "volume_up"
        elif "volume down" in clean_lower or "awaaz kam" in clean_lower or "quieter" in clean_lower:
            entities.action = "volume_down"
        elif "mute" in clean_lower or "unmute" in clean_lower or "chup" in clean_lower:
            entities.action = "mute"

        return entities
