"""
core/intent_classifier.py - Natural Language & Multilingual Intent Classifier for SYRAX
Supports English, Hindi, and Hinglish phrasing with typo/phonetic tolerance.
Categorizes full natural sentences and short voice utterances into structured intents.
"""

import re
from enum import Enum
from typing import Dict, List, Optional, Tuple


class IntentType(str, Enum):
    """Enumeration of all recognized user intents across supported applications."""
    # Playback & Media
    PLAY_MUSIC = "play_music"
    MEDIA_CONTROL = "media_control"
    VOLUME_CONTROL = "volume_control"

    # Specific Media & Task Stops
    STOP_MUSIC = "stop_music"
    STOP_VIDEO = "stop_video"
    STOP_SCROLLING = "stop_scrolling"
    CANCEL_MESSAGE = "cancel_message"
    CANCEL_OPERATION = "cancel_operation"

    # Specific Tab & Window Closes (Closes only SYRAX-opened instances)
    CLOSE_TAB = "close_tab"
    CLOSE_YOUTUBE = "close_youtube"
    CLOSE_INSTAGRAM = "close_instagram"
    CLOSE_WHATSAPP = "close_whatsapp"
    CLOSE_BROWSER = "close_browser"

    # Web & Navigation
    SEARCH_WEB = "search_web"
    OPEN_APP = "open_app"

    # Social & Messaging
    SCROLL_FEED = "scroll_feed"
    SEND_MESSAGE = "send_message"
    FIND_CONTACT = "find_contact"

    # System & Control
    INTERRUPT_STOP = "interrupt_stop"     # Generic stop activity without closing SYRAX
    EXIT_APP = "exit_app"                 # Explicitly shut down SYRAX
    GESTURE_MODE = "gesture_mode"
    DIAGNOSTICS = "diagnostics"
    GREETING = "greeting"
    CONFIRMATION = "confirmation"
    UNKNOWN = "unknown"


class IntentClassifier:
    """
    Rule-based, regex-driven, and phonetic-tolerant intent classifier.
    Handles complex natural language, filler words, and multilingual expressions.
    """

    # Hinglish & Hindi vocabulary indicators
    HINGLISH_MARKERS = {
        "ko", "ka", "ki", "ke", "karo", "kardo", "kijiye", "bhejo", "chalao", "bajao",
        "ruko", "roko", "band", "kholo", "dikhao", "sunao", "aage", "piche", "awaaz",
        "badhao", "kam", "haan", "nahin", "nahi", "mat", "bhai", "kripya", "chalu", "agla", "pichla"
    }

    def __init__(self) -> None:
        self._compile_matchers()

    def _compile_matchers(self) -> None:
        """Compile regex patterns for intent classification."""
        # Devanagari character detector
        self._re_devanagari = re.compile(r"[\u0900-\u097F]")

        # Specific Close Commands (Must be evaluated BEFORE generic stop/exit)
        self._re_close_youtube = re.compile(
            r"(?:\b(?:close\s+youtube|youtube\s+band\s*karo|youtube\s+close\s*karo)\b|यूट्यूब\s+बंद\s*करो)",
            re.IGNORECASE
        )
        self._re_close_instagram = re.compile(
            r"(?:\b(?:close\s+insta(?:gram)?|insta(?:gram)?\s+band\s*karo|insta(?:gram)?\s+close\s*karo)\b|इंस्टाग्राम\s+बंद\s*करो)",
            re.IGNORECASE
        )
        self._re_close_whatsapp = re.compile(
            r"(?:\b(?:close\s+whatsapp|whatsapp\s+band\s*karo|whatsapp\s+close\s*karo)\b|व्हाट्सएप\s+बंद\s*करो|व्हाट्सऐप\s+बंद\s*करो)",
            re.IGNORECASE
        )
        self._re_close_tab = re.compile(
            r"(?:\b(?:close\s+(?:this\s+)?(?:tab|page|website|site)|close\s+the\s+tab|tab\s+band\s*karo|page\s+band\s*karo)\b|टैब\s+बंद\s*करो)",
            re.IGNORECASE
        )
        self._re_close_browser = re.compile(
            r"(?:\b(?:close\s+(?:the\s+)?browser|close\s+chrome|close\s+edge|browser\s+band\s*karo)\b|ब्राउज़र\s+बंद\s*करो)",
            re.IGNORECASE
        )

        # Interrupt / Stop (Halts activity/playback, NEVER exits application)
        self._re_stop = re.compile(
            r"(?:\b(?:stop|cancel|ruko|roko|ruk\s*jao|band\s*karo|freeze|halt|abort|close\s+the\s+current\s+activity|stop\s+current\s+activity)\b|रुको|रुक\s*जाओ|रोको|बंद\s*करो|ठहरो|रुक)",
            re.IGNORECASE
        )

        # Specific stop variations
        self._re_stop_music = re.compile(
            r"(?:\b(?:stop\s+music|stop\s+song|gaana\s+band\s*karo|gaana\s+roko)\b|गाना\s+बंद\s*करो|गाना\s+रोको)",
            re.IGNORECASE
        )
        self._re_stop_video = re.compile(
            r"(?:\b(?:stop\s+video|video\s+band\s*karo|video\s+roko)\b|वीडियो\s+बंद\s*करो|वीडियो\s+रोको)",
            re.IGNORECASE
        )
        self._re_stop_scroll = re.compile(
            r"(?:\b(?:stop\s+scrolling|stop\s+scroll|scroll\s+roko)\b|स्क्रोल\s+रोको)",
            re.IGNORECASE
        )

        # Exit application specifically (must be distinct from stop)
        self._re_exit = re.compile(
            r"(?:\b(?:exit\s+syrax|close\s+syrax|quit\s+syrax|shut\s*down\s+syrax|close\s+assistant|exit\s+assistant|alvida)\b|अलविदा|सिरेक्स\s+बंद\s*करो|बाय\s+सिरेक्स)",
            re.IGNORECASE
        )

        # Confirmations (Yes / No)
        self._re_confirm_yes = re.compile(
            r"(?:\b(?:yes|yeah|yep|sure|send\s*it|send|haan|haan\s*bhejo|sahi\s*hai|theek\s*hai|ok|okay|proceed)\b|हाँ|हां|हां\s*भेजो|भेज\s*दो|भेजो)",
            re.IGNORECASE
        )
        self._re_confirm_no = re.compile(
            r"(?:\b(?:no|nope|cancel|don'?t\s*send|do\s*not\s*send|mat\s*bhejo|nahin|nahi|cancel\s*message)\b|मत\s*भेजो|नहीं|रद्द\s*करो)",
            re.IGNORECASE
        )

        # Messaging (WhatsApp)
        self._re_send_message = re.compile(
            r"(?:\b(?:send\s+(?:a\s+)?(?:whatsapp\s+)?message|message\s+bhejo|whatsapp\s+karo|send\s+text|text\s+bhejo|message\s+send\s+karo|find\s+.+\s+on\s+whatsapp\s+and\s+tell)\b|संदेश\s+भेजो|मैसेज\s+भेजो|व्हाट्सएप\s+करो)",
            re.IGNORECASE
        )
        self._re_find_contact = re.compile(
            r"(?:\b(?:find\s+.+\s+on\s+whatsapp|open\s+.+'s\s+chat|open\s+whatsapp\s+chats?|whatsapp\s+pe\s+.+\s+dhoondo)\b|व्हाट्सएप\s+पर\s+.+\s+ढूंढो)",
            re.IGNORECASE
        )

        # Feed & Reels Scrolling (Instagram)
        self._re_scroll = re.compile(
            r"(?:\b(?:scroll(?:\s+reels|\s+feed|\s+down|\s+up)?|next\s+reel|previous\s+reel|reel\s+badlo|agla\s+reel|pichla\s+reel|neeche\s+scroll|upar\s+scroll)\b|रील्स\s+दिखाओ|अगली\s+रील|पिछली\s+रील|स्क्रोल\s+करो)",
            re.IGNORECASE
        )

        # Music & Playback
        self._re_play = re.compile(
            r"(?:\b(?:play|stream|listen\s+to|let'?s\s+watch|i\s+want\s+to\s+listen\s+to|can\s+you\s+play|chalao|bajao|sunao|gaana\s+chalao|song\s+lagao)\b|चलाओ|बजाओ|सुनाओ|गाना\s+चलाओ|गाना\s+लगाओ)",
            re.IGNORECASE
        )

        # Web Search
        self._re_search = re.compile(
            r"(?:\b(?:search(?:\s+for)?|google(?:\s+for)?|look\s+up|find(?:\s+me)?|khojo|dhoondo)\b|खोजो|ढूंढो)",
            re.IGNORECASE
        )

        # App Launching
        self._re_open_app = re.compile(
            r"\b(?:open|launch|start|goto|go\s+to|kholo|खोलो)\s+([a-zA-Z0-9_\s\u0900-\u097F]+)",
            re.IGNORECASE
        )

        # Media controls (Pause, Resume, Next, Prev, Forward, Rewind)
        self._re_media_pause = re.compile(
            r"(?:\b(?:pause(?:\s+the|\s+this)?(?:\s+for\s+a\s+moment)?(?:\s+music|\s+video|\s+playback)?|hold|gaana\s+roko)\b|पॉज़|रोको)",
            re.IGNORECASE
        )
        self._re_media_resume = re.compile(
            r"(?:\b(?:resume(?:\s+the)?(?:\s+music|\s+video|\s+playback)?|unpause|continue\s+playback|play\s+again|play\s+it\s+again|gaana\s+chalu\s*karo)\b|फिर\s+से\s+चलाओ)",
            re.IGNORECASE
        )
        self._re_media_next = re.compile(
            r"(?:\b(?:next(?:\s+song|\s+video|\s+track)?|skip(?:\s+track|\s+song)?|agla\s+gaana)\b|अगला\s+गाना|अगला\s+वीडियो)",
            re.IGNORECASE
        )
        self._re_media_prev = re.compile(
            r"(?:\b(?:previous(?:\s+song|\s+video|\s+track)?|prev|pichla\s+gaana|piche\s+karo)\b|पिछला\s+गाना)",
            re.IGNORECASE
        )
        self._re_media_forward = re.compile(
            r"(?:\b(?:forward|fast\s+forward|skip\s+forward|aage\s+karo)\b|आगे\s+करो)",
            re.IGNORECASE
        )
        self._re_media_rewind = re.compile(
            r"(?:\b(?:rewind|backward|skip\s+backward|piche\s+karo)\b|पीछे\s+करो)",
            re.IGNORECASE
        )

        # Volume Controls
        self._re_volume_up = re.compile(
            r"(?:\b(?:volume\s+up|increase\s+volume|turn\s+(?:it\s+)?up|louder|awaaz\s+badhao|awaaz\s+tez)\b|आवाज़\s+बढ़ाओ|आवाज़\s+तेज़)",
            re.IGNORECASE
        )
        self._re_volume_down = re.compile(
            r"(?:\b(?:volume\s+down|decrease\s+volume|turn\s+(?:it\s+)?down|quieter|awaaz\s+kam|awaaz\s+dheemi)\b|आवाज़\s+कम\s*करो|आवाज़\s+धीमी)",
            re.IGNORECASE
        )
        self._re_volume_mute = re.compile(
            r"(?:\b(?:mute|unmute|silence|chup\s+ho\s*jao|awaaz\s+band)\b|शांत|म्यूट|आवाज़\s+बंद)",
            re.IGNORECASE
        )

        # Gesture Mode
        self._re_gesture_mode = re.compile(
            r"\b(?:start|stop|activate|deactivate|enable|disable|turn\s+on|turn\s+off|exit)\s+gesture\s+mode\b|\bgesture\s+mode\s+(?:on|off|start|stop)\b|\bजेस्चर\s+मोड\b",
            re.IGNORECASE
        )

        # Diagnostics & Greeting
        self._re_diagnostics = re.compile(
            r"\b(?:run\s+diagnostics|self\s+test|system\s+test|diagnose)\b",
            re.IGNORECASE
        )
        self._re_greeting = re.compile(
            r"^(?:hello|hi|hey|greetings|good\s+(?:morning|afternoon|evening)|namaste|kaise\s+ho|नमस्ते|नमस्कार|प्रणाम)(?:\s+syrax)?$",
            re.IGNORECASE
        )

    def detect_language(self, text: str) -> str:
        """Heuristic language detection between English, Hindi (Devanagari), and Hinglish."""
        if self._re_devanagari.search(text):
            return "hindi"
        tokens = re.findall(r"\b[a-zA-Z]+\b", text.lower())
        hinglish_count = sum(1 for t in tokens if t in self.HINGLISH_MARKERS)
        if hinglish_count >= 1:
            return "hinglish"
        return "english"

    def classify(self, text: str) -> Tuple[IntentType, float, str]:
        """
        Classifies input text into a primary IntentType.
        Returns (IntentType, confidence, language_guess).
        """
        clean = text.strip()
        if not clean:
            return IntentType.UNKNOWN, 0.0, "english"

        lang = self.detect_language(clean)

        # 1. Exit Check First (High Priority)
        if self._re_exit.search(clean):
            return IntentType.EXIT_APP, 1.0, lang

        # 2. Specific Close Commands (Close Tab/YouTube/Instagram/WhatsApp/Browser)
        if self._re_close_youtube.search(clean):
            return IntentType.CLOSE_YOUTUBE, 1.0, lang
        if self._re_close_instagram.search(clean):
            return IntentType.CLOSE_INSTAGRAM, 1.0, lang
        if self._re_close_whatsapp.search(clean):
            return IntentType.CLOSE_WHATSAPP, 1.0, lang
        if self._re_close_tab.search(clean):
            return IntentType.CLOSE_TAB, 1.0, lang
        if self._re_close_browser.search(clean):
            return IntentType.CLOSE_BROWSER, 1.0, lang

        # 3. Stop / Interrupt Check (High Priority - Activity stop, never exits app)
        if self._re_stop_music.search(clean):
            return IntentType.STOP_MUSIC, 1.0, lang
        if self._re_stop_video.search(clean):
            return IntentType.STOP_VIDEO, 1.0, lang
        if self._re_stop_scroll.search(clean):
            return IntentType.STOP_SCROLLING, 1.0, lang
        if self._re_stop.search(clean):
            # Check if specifically stopping gesture mode
            if "gesture" in clean.lower() or "जेस्चर" in clean:
                return IntentType.GESTURE_MODE, 0.95, lang
            return IntentType.INTERRUPT_STOP, 1.0, lang

        # 4. WhatsApp / Messaging Check (Before broad confirmation matching)
        clean_lower = clean.lower()
        if self._re_send_message.search(clean) or ("message" in clean_lower and any(w in clean_lower for w in ("bhejo", "send", "to", "ko", "tell"))):
            return IntentType.SEND_MESSAGE, 0.95, lang

        if self._re_find_contact.search(clean) or ("whatsapp" in clean_lower and "chat" in clean_lower):
            return IntentType.FIND_CONTACT, 0.90, lang

        # 5. Confirmation Yes / No (Explicit conversational affirmations / cancellations)
        if clean_lower in ("yes", "send", "send it", "haan", "haan bhejo", "sahi hai", "theek hai", "हाँ", "हां", "भेजो"):
            return IntentType.CONFIRMATION, 1.0, lang
        if clean_lower in ("no", "don't send", "dont send", "mat bhejo", "nahin", "nahi", "cancel", "मत भेजो", "नहीं"):
            return IntentType.CONFIRMATION, 1.0, lang
        if self._re_confirm_yes.search(clean) and len(clean.split()) <= 3 and not any(w in clean_lower for w in ("message", "to", "ko")):
            return IntentType.CONFIRMATION, 0.90, lang
        if self._re_confirm_no.search(clean) and len(clean.split()) <= 3 and not any(w in clean_lower for w in ("message", "to", "ko")):
            return IntentType.CONFIRMATION, 0.90, lang

        # 6. Gesture Mode Controls
        if self._re_gesture_mode.search(clean):
            return IntentType.GESTURE_MODE, 0.95, lang

        # 7. Instagram / Reels Scrolling
        if self._re_scroll.search(clean):
            return IntentType.SCROLL_FEED, 0.95, lang

        # 8. Diagnostics
        if self._re_diagnostics.search(clean):
            return IntentType.DIAGNOSTICS, 1.0, lang

        # 9. Greetings
        if self._re_greeting.search(clean):
            return IntentType.GREETING, 1.0, lang

        # 10. Volume Controls
        if self._re_volume_up.search(clean) or self._re_volume_down.search(clean) or self._re_volume_mute.search(clean):
            return IntentType.VOLUME_CONTROL, 0.95, lang

        # 11. Media Playback Controls (Pause / Resume / Next / Prev / Fwd / Rewind)
        if (
            self._re_media_pause.search(clean)
            or self._re_media_resume.search(clean)
            or self._re_media_next.search(clean)
            or self._re_media_prev.search(clean)
            or self._re_media_forward.search(clean)
            or self._re_media_rewind.search(clean)
        ):
            return IntentType.MEDIA_CONTROL, 0.95, lang

        # 12. Music Playback ("Play Barsaat by Banjare", "gaana chalao", "let's watch...")
        if self._re_play.search(clean):
            return IntentType.PLAY_MUSIC, 0.92, lang

        # 13. Search ("Search for relaxing music on YouTube", "Google machine learning")
        if self._re_search.search(clean):
            return IntentType.SEARCH_WEB, 0.90, lang

        # 14. App / Site Open ("Open Instagram", "Open WhatsApp", "Launch YouTube")
        open_match = self._re_open_app.search(clean)
        if open_match:
            target = open_match.group(1).strip().lower()
            known_targets = ("youtube", "instagram", "insta", "whatsapp", "google", "github", "chrome", "edge", "browser", "यूट्यूब", "इंस्टाग्राम", "व्हाट्सएप")
            if any(k in target for k in known_targets):
                return IntentType.OPEN_APP, 0.95, lang

        return IntentType.UNKNOWN, 0.3, lang

        return IntentType.UNKNOWN, 0.3, lang
