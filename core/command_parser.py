"""
core/command_parser.py - Natural Language Command Parser for SYRAX
Transforms raw voice transcripts and typed text into structured Command objects
using Regex, Keyword Matching, Entity Extraction, and Intent Classification, with
full support for English, Hindi, and Hinglish phrasing.
"""

import difflib
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import config
from core.conversation_state import ConversationState
from core.entity_extractor import EntityExtractor, ExtractedEntities
from core.intent_classifier import IntentClassifier, IntentType
from core.interrupt_manager import InterruptManager, InterruptType
from core.logger import get_logger

logger = get_logger("CommandParser")


class CommandIntent(str, Enum):
    """Categorized intent types supported by the SYRAX action pipeline."""
    GREETING = "greeting"
    OPEN_SITE = "open_site"
    SEARCH = "search"
    PLAY = "play"
    MEDIA_CONTROL = "media_control"
    VOLUME_CONTROL = "volume_control"
    PRESENTATION_CONTROL = "presentation_control"
    GESTURE_MODE = "gesture_mode"
    DIAGNOSTICS = "diagnostics"
    EXIT = "exit"
    STOP = "stop"                       # Halt active task, search, or playback without exiting
    STOP_MUSIC = "stop_music"
    STOP_VIDEO = "stop_video"
    STOP_SCROLLING = "stop_scrolling"
    CANCEL_MESSAGE = "cancel_message"
    CANCEL_OPERATION = "cancel_operation"
    CLOSE_TAB = "close_tab"
    CLOSE_YOUTUBE = "close_youtube"
    CLOSE_INSTAGRAM = "close_instagram"
    CLOSE_WHATSAPP = "close_whatsapp"
    CLOSE_BROWSER = "close_browser"
    SCROLL_FEED = "scroll_feed"         # Reels / page feed scrolling
    SEND_MESSAGE = "send_message"       # WhatsApp message dispatch
    FIND_CONTACT = "find_contact"       # WhatsApp contact lookup
    CONFIRMATION = "confirmation"       # Multi-turn spoken confirmation
    UNKNOWN = "unknown"


@dataclass
class Command:
    """Structured representation of a parsed command."""
    intent: CommandIntent
    action: Optional[str] = None
    target: Optional[str] = None
    query: Optional[str] = None
    parameters: Dict[str, Any] = field(default_factory=dict)
    raw_text: str = ""
    confidence: float = 1.0
    source: str = "voice"
    language_guess: str = "english"
    entities: Optional[ExtractedEntities] = None


class CommandParser:
    """
    Multi-stage natural language intent parser:
    1. Wake-word prefix normalization ('SYRAX, ...')
    2. High-priority interrupt detection (immediate stop/cancel)
    3. Multi-turn conversation slot and confirmation resolution
    4. Deterministic regex & keyword pattern rules
    5. Natural language intent classification & entity extraction
    6. Fuzzy matching fallback via difflib
    """

    # Canonical phrase anchors for fuzzy matching fallback
    CANONICAL_PHRASES = {
        "hello syrax": (CommandIntent.GREETING, None, None),
        "hi syrax": (CommandIntent.GREETING, None, None),
        "hey syrax": (CommandIntent.GREETING, None, None),
        "open youtube": (CommandIntent.OPEN_SITE, "open", "youtube"),
        "open google": (CommandIntent.OPEN_SITE, "open", "google"),
        "open github": (CommandIntent.OPEN_SITE, "open", "github"),
        "open instagram": (CommandIntent.OPEN_SITE, "open", "instagram"),
        "open whatsapp": (CommandIntent.OPEN_SITE, "open", "whatsapp"),
        "pause video": (CommandIntent.MEDIA_CONTROL, "pause", None),
        "pause music": (CommandIntent.MEDIA_CONTROL, "pause", None),
        "resume video": (CommandIntent.MEDIA_CONTROL, "resume", None),
        "play music": (CommandIntent.MEDIA_CONTROL, "resume", None),
        "next video": (CommandIntent.MEDIA_CONTROL, "next", None),
        "next track": (CommandIntent.MEDIA_CONTROL, "next", None),
        "previous video": (CommandIntent.MEDIA_CONTROL, "previous", None),
        "fast forward": (CommandIntent.MEDIA_CONTROL, "forward", None),
        "forward": (CommandIntent.MEDIA_CONTROL, "forward", None),
        "rewind": (CommandIntent.MEDIA_CONTROL, "rewind", None),
        "volume up": (CommandIntent.VOLUME_CONTROL, "volume_up", None),
        "volume down": (CommandIntent.VOLUME_CONTROL, "volume_down", None),
        "mute": (CommandIntent.VOLUME_CONTROL, "mute", None),
        "close assistant": (CommandIntent.EXIT, "shutdown", None),
        "exit": (CommandIntent.EXIT, "shutdown", None),
        "run diagnostics": (CommandIntent.DIAGNOSTICS, "run", None),
        "start gesture mode": (CommandIntent.GESTURE_MODE, "start", None),
        "stop gesture mode": (CommandIntent.GESTURE_MODE, "stop", None),
        "activate gesture mode": (CommandIntent.GESTURE_MODE, "start", None),
        "exit gesture mode": (CommandIntent.GESTURE_MODE, "stop", None),
        "scroll reels": (CommandIntent.SCROLL_FEED, "scroll_down", "instagram"),
        "close youtube": (CommandIntent.CLOSE_YOUTUBE, "close", "youtube"),
        "close instagram": (CommandIntent.CLOSE_INSTAGRAM, "close", "instagram"),
        "close whatsapp": (CommandIntent.CLOSE_WHATSAPP, "close", "whatsapp"),
        "close tab": (CommandIntent.CLOSE_TAB, "close", "tab"),
        "close this tab": (CommandIntent.CLOSE_TAB, "close", "tab"),
        "close this website": (CommandIntent.CLOSE_TAB, "close", "tab"),
        "close page": (CommandIntent.CLOSE_TAB, "close", "tab"),
        "close browser": (CommandIntent.CLOSE_BROWSER, "close", "browser"),
        "close the browser": (CommandIntent.CLOSE_BROWSER, "close", "browser"),
        "stop music": (CommandIntent.STOP_MUSIC, "stop", "music"),
        "stop video": (CommandIntent.STOP_VIDEO, "stop", "video"),
        "stop scrolling": (CommandIntent.STOP_SCROLLING, "stop", "scrolling"),
        "pause it": (CommandIntent.MEDIA_CONTROL, "pause", None),
        "play again": (CommandIntent.MEDIA_CONTROL, "resume", None),
        "play it again": (CommandIntent.MEDIA_CONTROL, "resume", None),
    }

    # Wake word prefix pattern
    RE_WAKE_PREFIX = re.compile(
        r"^(?:(?:hey|hi|hello|ok|okay)?\s*syrax[\s,:]*)+",
        re.IGNORECASE
    )

    def __init__(
        self,
        conversation_state: Optional[ConversationState] = None,
        interrupt_manager: Optional[InterruptManager] = None
    ) -> None:
        self.conversation_state = conversation_state or ConversationState()
        self.interrupt_manager = interrupt_manager or InterruptManager()
        self.intent_classifier = IntentClassifier()
        self.entity_extractor = EntityExtractor()
        self._compile_patterns()

    def _compile_patterns(self) -> None:
        """Compile regex matchers for optimal runtime performance."""
        # Greetings
        self._pattern_greeting = re.compile(
            r"^(?:hello|hi|hey|greetings|good\s+(?:morning|afternoon|evening)|namaste)(?:\s+syrax)?$",
            re.IGNORECASE
        )

        # Open Site variations: "open youtube", "launch google", "go to github"
        all_sites = list(config.QUICK_SITES.keys()) + ["browser", "my browser", "web browser", "the browser"]
        site_names = "|".join(re.escape(s) for s in all_sites)
        self._pattern_open_site = re.compile(
            rf"^(?:open|launch|go\s+to|start|navigate\s+to|browse\s+to)\s+({site_names})\b",
            re.IGNORECASE
        )

        # Search Web variations: "search python tutorial", "google machine learning"
        self._pattern_search = re.compile(
            r"^(?:search(?:\s+for)?|google|look\s+up|find)\s+(.+)$",
            re.IGNORECASE
        )

        # Play query on YouTube: "play python tutorial", "play bohemian rhapsody"
        self._pattern_play = re.compile(
            r"^(?:play|stream|listen\s+to)\s+(?!music$|video$|playback$|again$|it\s+again$)(.+)$",
            re.IGNORECASE
        )

        # Media Controls
        self._pattern_pause = re.compile(
            r"^(?:pause(?:\s+the)?(?:\s+video|\s+music|\s+playback)?|stop\s+music|stop\s+playback|hold|freeze\s+video)$",
            re.IGNORECASE
        )
        self._pattern_resume = re.compile(
            r"^(?:play\s+music|play\s+video|play\s+again|play\s+it\s+again|resume(?:\s+the)?(?:\s+video|\s+music|\s+playback)?|continue(?:\s+playback)?|unpause)$",
            re.IGNORECASE
        )
        self._pattern_next = re.compile(
            r"^(?:next(?:\s+video|\s+track|\s+song)?|skip(?:\s+video|\s+track|\s+song)?)$",
            re.IGNORECASE
        )
        self._pattern_prev = re.compile(
            r"^(?:previous(?:\s+video|\s+track|\s+song)?|prev(?:\s+video|\s+track)?|back(?:\s+track|\s+song)?)$",
            re.IGNORECASE
        )
        self._pattern_forward = re.compile(
            r"^(?:forward|fast\s+forward|skip\s+forward|forward\s+10\s+seconds|jump\s+forward)$",
            re.IGNORECASE
        )
        self._pattern_rewind = re.compile(
            r"^(?:rewind|go\s+back|skip\s+back|rewind\s+10\s+seconds|jump\s+back)$",
            re.IGNORECASE
        )

        # Volume Controls
        self._pattern_volume_up = re.compile(
            r"^(?:volume\s+up|increase\s+volume|turn\s+(?:it\s+)?up|raise\s+volume|louder)(?:\s+by)?(?:\s+(\d+))?$",
            re.IGNORECASE
        )
        self._pattern_volume_down = re.compile(
            r"^(?:volume\s+down|decrease\s+volume|turn\s+(?:it\s+)?down|lower\s+volume|quieter)(?:\s+by)?(?:\s+(\d+))?$",
            re.IGNORECASE
        )
        self._pattern_mute = re.compile(
            r"^(?:mute(?:\s+volume|\s+audio)?|unmute|silence)$",
            re.IGNORECASE
        )

        # Close Specific App / Tab / Browser
        self._pattern_close_youtube = re.compile(
            r"^(?:close\s+youtube|youtube\s+band\s*karo|यूट्यूब\s+बंद\s*करो)$",
            re.IGNORECASE
        )
        self._pattern_close_instagram = re.compile(
            r"^(?:close\s+insta(?:gram)?|insta(?:gram)?\s+band\s*karo|इंस्टाग्राम\s+बंद\s*करो)$",
            re.IGNORECASE
        )
        self._pattern_close_whatsapp = re.compile(
            r"^(?:close\s+whatsapp|whatsapp\s+band\s*karo|व्हाट्सएप\s+बंद\s*करो)$",
            re.IGNORECASE
        )
        self._pattern_close_tab = re.compile(
            r"^(?:close\s+(?:this\s+)?(?:tab|page|website|site)|close\s+the\s+tab|tab\s+band\s*karo|टैब\s+बंद\s*करो)$",
            re.IGNORECASE
        )
        self._pattern_close_browser = re.compile(
            r"^(?:close\s+(?:the\s+)?browser|close\s+chrome|close\s+edge|browser\s+band\s*karo|ब्राउज़र\s+बंद\s*करो)$",
            re.IGNORECASE
        )

        # Stop specific tasks
        self._pattern_stop_music = re.compile(
            r"^(?:stop\s+music|stop\s+song|gaana\s+band\s*karo|गाना\s+बंद\s*करो)$",
            re.IGNORECASE
        )
        self._pattern_stop_video = re.compile(
            r"^(?:stop\s+video|video\s+band\s*karo|वीडियो\s+बंद\s*करो)$",
            re.IGNORECASE
        )
        self._pattern_stop_scroll = re.compile(
            r"^(?:stop\s+scrolling|stop\s+scroll|scroll\s+roko|स्क्रोल\s+रोको)$",
            re.IGNORECASE
        )

        # Exit / Shutdown
        self._pattern_exit = re.compile(
            r"^(?:close\s+assistant|close\s+syrax|exit(?:\s+syrax)?|quit(?:\s+syrax)?|shut\s*down(?:\s+syrax)?|goodbye|bye|alvida|अलविदा|सिरेक्स\s+बंद\s*करो)$",
            re.IGNORECASE
        )

        # Diagnostics
        self._pattern_diagnostics = re.compile(
            r"^(?:run\s+diagnostics|diagnostics|self\s+test|system\s+test|diagnose(?:\s+system)?)$",
            re.IGNORECASE
        )

        # Gesture Mode Toggle
        self._pattern_gesture_mode_start = re.compile(
            r"^(?:(?:start|activate|enable|turn\s+on)\s+gesture\s+mode|gesture\s+mode\s+(?:on|start|active))$",
            re.IGNORECASE
        )
        self._pattern_gesture_mode_stop = re.compile(
            r"^(?:(?:stop|deactivate|disable|exit|turn\s+off)\s+gesture\s+mode|gesture\s+mode\s+(?:off|stop|idle|exit))$",
            re.IGNORECASE
        )

    def parse(self, raw_input: str, source: str = "voice") -> Command:
        """
        Main parsing entry point. Sanitizes input, strips wake word prefix,
        resolves multi-turn context, checks high-priority interrupts, and determines intent.
        """
        if not raw_input or not raw_input.strip():
            return Command(
                intent=CommandIntent.UNKNOWN,
                raw_text=raw_input,
                confidence=0.0,
                source=source
            )

        text = raw_input.strip()

        # 1. Strip wake-word prefix ("SYRAX, play Barsaat" -> "play Barsaat")
        normalized_text = self.RE_WAKE_PREFIX.sub("", text).strip()
        if not normalized_text:
            # Utterance was purely the wake word: "SYRAX"
            return Command(
                intent=CommandIntent.GREETING,
                raw_text=text,
                confidence=1.0,
                source=source
            )

        cleaned = self._clean_text(normalized_text)
        lang = self.intent_classifier.detect_language(normalized_text)

        # 2. Check for Urgent Interrupts (Stop / Cancel / Exit)
        interrupt_type = self.interrupt_manager.check_for_interrupt_phrase(normalized_text)
        if interrupt_type == InterruptType.EXIT_SYRAX:
            return Command(
                intent=CommandIntent.EXIT,
                action="shutdown",
                raw_text=text,
                confidence=1.0,
                source=source,
                language_guess=lang
            )
        elif interrupt_type == InterruptType.STOP_GESTURES:
            return Command(
                intent=CommandIntent.GESTURE_MODE,
                action="stop",
                raw_text=text,
                confidence=1.0,
                source=source,
                language_guess=lang
            )
        elif interrupt_type == InterruptType.CANCEL_MESSAGE:
            self.conversation_state.clear_pending_confirmation()
            return Command(
                intent=CommandIntent.CONFIRMATION,
                action="cancel",
                raw_text=text,
                confidence=1.0,
                source=source,
                language_guess=lang
            )
        elif interrupt_type == InterruptType.PAUSE:
            return Command(
                intent=CommandIntent.MEDIA_CONTROL,
                action="pause",
                raw_text=text,
                confidence=1.0,
                source=source,
                language_guess=lang
            )
        elif interrupt_type == InterruptType.STOP_ACTIVITY:
            self.conversation_state.reset_all_pending()
            return Command(
                intent=CommandIntent.STOP,
                action="stop",
                raw_text=text,
                confidence=1.0,
                source=source,
                language_guess=lang
            )

        # 3. Check Conversation State for Multi-Turn Dialogs
        # 3a. Pending confirmation (e.g. WhatsApp send prompt)
        pending_conf = self.conversation_state.get_pending_confirmation()
        if pending_conf:
            lower = normalized_text.lower()
            if any(w in lower for w in ("yes", "send", "send it", "haan", "haan bhejo", "sahi hai", "theek hai")):
                return Command(
                    intent=CommandIntent.CONFIRMATION,
                    action="confirm",
                    parameters={"action_type": pending_conf.action_type, "recipient": pending_conf.recipient, "content": pending_conf.content},
                    raw_text=text,
                    confidence=1.0,
                    source=source,
                    language_guess=lang
                )
            elif any(w in lower for w in ("no", "don't send", "dont send", "cancel", "mat bhejo", "nahin", "nahi")):
                self.conversation_state.clear_pending_confirmation()
                return Command(
                    intent=CommandIntent.CONFIRMATION,
                    action="cancel",
                    parameters={"action_type": pending_conf.action_type, "recipient": pending_conf.recipient},
                    raw_text=text,
                    confidence=1.0,
                    source=source,
                    language_guess=lang
                )

        # 3b. Pending Slot Resolution (e.g. "What song would you like to hear?" -> "Barsaat by Banjare")
        pending_slot_info = self.conversation_state.get_pending_slot()
        if pending_slot_info:
            slot_name, target_intent, initial_data = pending_slot_info
            self.conversation_state.clear_pending_slot()

            if slot_name == "song_title":
                entities = self.entity_extractor.extract(f"play {normalized_text}")
                q = entities.query or normalized_text
                return Command(
                    intent=CommandIntent.PLAY,
                    action="play",
                    query=q,
                    parameters={"song_title": entities.song_title or normalized_text, "artist": entities.artist, "query": q, "app": "youtube"},
                    raw_text=text,
                    confidence=0.95,
                    source=source,
                    language_guess=lang,
                    entities=entities
                )
            elif slot_name == "message_content":
                recipient = initial_data.get("contact", "Contact")
                return Command(
                    intent=CommandIntent.SEND_MESSAGE,
                    action="draft_content",
                    target=recipient,
                    query=normalized_text,
                    parameters={"contact": recipient, "message": normalized_text, "app": "whatsapp"},
                    raw_text=text,
                    confidence=0.95,
                    source=source,
                    language_guess=lang
                )

        # 4. Deterministic Regex Rules (Preserves baseline compatibility)
        cmd = self._match_rules(cleaned, text, source)
        if cmd is not None:
            # Enrich with extracted entities if present
            entities = self.entity_extractor.extract(normalized_text, intent_hint=cmd.intent.value)
            cmd.entities = entities
            cmd.language_guess = lang
            if entities.song_title:
                cmd.parameters["song_title"] = entities.song_title
            if entities.artist:
                cmd.parameters["artist"] = entities.artist
            return cmd

        # 5. Natural Language Intent Classification & Entity Extraction
        classified_intent, intent_conf, detected_lang = self.intent_classifier.classify(normalized_text)
        entities = self.entity_extractor.extract(normalized_text, intent_hint=classified_intent.value)

        if classified_intent == IntentType.PLAY_MUSIC:
            q = entities.query or normalized_text
            return Command(
                intent=CommandIntent.PLAY,
                action="play",
                query=q,
                parameters={
                    "song_title": entities.song_title,
                    "artist": entities.artist,
                    "query": q,
                    "app": entities.app_name or "youtube",
                    "needs_slot": entities.extra_params.get("needs_slot", False)
                },
                raw_text=text,
                confidence=intent_conf,
                source=source,
                language_guess=detected_lang,
                entities=entities
            )

        elif classified_intent == IntentType.SEND_MESSAGE:
            contact = entities.contact_name or self.conversation_state.last_contact
            if contact:
                self.conversation_state.last_contact = contact
            return Command(
                intent=CommandIntent.SEND_MESSAGE,
                action="send",
                target=contact,
                query=entities.message_content,
                parameters={
                    "contact": contact,
                    "message": entities.message_content,
                    "app": "whatsapp"
                },
                raw_text=text,
                confidence=intent_conf,
                source=source,
                language_guess=detected_lang,
                entities=entities
            )

        elif classified_intent == IntentType.FIND_CONTACT:
            return Command(
                intent=CommandIntent.FIND_CONTACT,
                action="find",
                target=entities.contact_name,
                parameters={"contact": entities.contact_name, "app": "whatsapp"},
                raw_text=text,
                confidence=intent_conf,
                source=source,
                language_guess=detected_lang,
                entities=entities
            )

        elif classified_intent == IntentType.SCROLL_FEED:
            return Command(
                intent=CommandIntent.SCROLL_FEED,
                action=entities.action or "scroll_down",
                parameters={"app": "instagram"},
                raw_text=text,
                confidence=intent_conf,
                source=source,
                language_guess=detected_lang,
                entities=entities
            )

        elif classified_intent == IntentType.SEARCH_WEB:
            return Command(
                intent=CommandIntent.SEARCH,
                action="search",
                query=entities.query or normalized_text,
                parameters={"query": entities.query or normalized_text, "app": entities.app_name or "google"},
                raw_text=text,
                confidence=intent_conf,
                source=source,
                language_guess=detected_lang,
                entities=entities
            )

        elif classified_intent == IntentType.OPEN_APP:
            target_app = entities.app_name or "browser"
            return Command(
                intent=CommandIntent.OPEN_SITE,
                action="open",
                target=target_app,
                parameters={"url": config.QUICK_SITES.get(target_app, "")},
                raw_text=text,
                confidence=intent_conf,
                source=source,
                language_guess=detected_lang,
                entities=entities
            )

        elif classified_intent == IntentType.MEDIA_CONTROL:
            return Command(
                intent=CommandIntent.MEDIA_CONTROL,
                action=entities.action or "toggle",
                raw_text=text,
                confidence=intent_conf,
                source=source,
                language_guess=detected_lang,
                entities=entities
            )

        elif classified_intent == IntentType.VOLUME_CONTROL:
            action = entities.action or ("volume_up" if "up" in normalized_text.lower() or "badhao" in normalized_text.lower() else "volume_down")
            amt = int(entities.numeric_value) if entities.numeric_value else 10
            return Command(
                intent=CommandIntent.VOLUME_CONTROL,
                action=action,
                parameters={"amount": amt},
                raw_text=text,
                confidence=intent_conf,
                source=source,
                language_guess=detected_lang,
                entities=entities
            )

        elif classified_intent == IntentType.INTERRUPT_STOP:
            self.conversation_state.reset_all_pending()
            return Command(
                intent=CommandIntent.STOP,
                action="stop",
                raw_text=text,
                confidence=intent_conf,
                source=source,
                language_guess=detected_lang
            )

        elif classified_intent == IntentType.CLOSE_YOUTUBE:
            return Command(
                intent=CommandIntent.CLOSE_YOUTUBE,
                action="close",
                target="youtube",
                raw_text=text,
                confidence=intent_conf,
                source=source,
                language_guess=detected_lang
            )

        elif classified_intent == IntentType.CLOSE_INSTAGRAM:
            return Command(
                intent=CommandIntent.CLOSE_INSTAGRAM,
                action="close",
                target="instagram",
                raw_text=text,
                confidence=intent_conf,
                source=source,
                language_guess=detected_lang
            )

        elif classified_intent == IntentType.CLOSE_WHATSAPP:
            return Command(
                intent=CommandIntent.CLOSE_WHATSAPP,
                action="close",
                target="whatsapp",
                raw_text=text,
                confidence=intent_conf,
                source=source,
                language_guess=detected_lang
            )

        elif classified_intent == IntentType.CLOSE_TAB:
            return Command(
                intent=CommandIntent.CLOSE_TAB,
                action="close",
                target="tab",
                raw_text=text,
                confidence=intent_conf,
                source=source,
                language_guess=detected_lang
            )

        elif classified_intent == IntentType.CLOSE_BROWSER:
            return Command(
                intent=CommandIntent.CLOSE_BROWSER,
                action="close",
                target="browser",
                raw_text=text,
                confidence=intent_conf,
                source=source,
                language_guess=detected_lang
            )

        elif classified_intent == IntentType.STOP_MUSIC:
            return Command(
                intent=CommandIntent.STOP_MUSIC,
                action="stop",
                target="music",
                raw_text=text,
                confidence=intent_conf,
                source=source,
                language_guess=detected_lang
            )

        elif classified_intent == IntentType.STOP_VIDEO:
            return Command(
                intent=CommandIntent.STOP_VIDEO,
                action="stop",
                target="video",
                raw_text=text,
                confidence=intent_conf,
                source=source,
                language_guess=detected_lang
            )

        elif classified_intent == IntentType.STOP_SCROLLING:
            return Command(
                intent=CommandIntent.STOP_SCROLLING,
                action="stop",
                target="scrolling",
                raw_text=text,
                confidence=intent_conf,
                source=source,
                language_guess=detected_lang
            )

        elif classified_intent == IntentType.EXIT_APP:
            return Command(
                intent=CommandIntent.EXIT,
                action="shutdown",
                raw_text=text,
                confidence=intent_conf,
                source=source,
                language_guess=detected_lang
            )

        # 6. Fuzzy Matching Fallback (difflib)
        fuzzy_cmd = self._match_fuzzy(cleaned, text, source)
        if fuzzy_cmd is not None:
            return fuzzy_cmd

        # 7. Unrecognized Intent
        logger.info(f"Unrecognized command: '{text}'")
        return Command(
            intent=CommandIntent.UNKNOWN,
            raw_text=text,
            confidence=0.0,
            source=source,
            language_guess=lang
        )

    def _clean_text(self, text: str) -> str:
        """Normalize punctuation and whitespace."""
        cleaned = re.sub(r"[^\w\s]", " ", text.lower())
        return " ".join(cleaned.split())

    def _match_rules(self, text: str, original: str, source: str) -> Optional[Command]:
        """Evaluate deterministic regex rules against normalized text."""
        # Greeting
        if self._pattern_greeting.match(text):
            return Command(
                intent=CommandIntent.GREETING,
                raw_text=original,
                confidence=1.0,
                source=source
            )

        # Open Site & Compound Navigation
        if "instagram" in text and ("reel" in text or "scroll" in text):
            return Command(
                intent=CommandIntent.OPEN_SITE,
                action="open_reels",
                target="instagram",
                parameters={"url": "https://www.instagram.com/reels/", "mode": "reels", "secondary_action": "scroll_reels"},
                raw_text=original,
                confidence=1.0,
                source=source
            )

        m_site = self._pattern_open_site.match(text)
        if m_site:
            raw_target = m_site.group(1).lower()
            site_key = "browser" if "browser" in raw_target else raw_target
            return Command(
                intent=CommandIntent.OPEN_SITE,
                action="open",
                target=site_key,
                parameters={"url": config.QUICK_SITES.get(site_key, "")},
                raw_text=original,
                confidence=1.0,
                source=source
            )

        # Search Web
        if not any(k in text for k in ("whatsapp", "message", "tell", "bhejo")):
            m_search = self._pattern_search.match(text)
            if m_search:
                raw_q = m_search.group(1).strip()
                m_target = re.search(r"^(.+?)\s+on\s+([a-zA-Z0-9_]+)$", raw_q, re.IGNORECASE)
                if m_target:
                    q = m_target.group(1).strip()
                    t_app = m_target.group(2).strip().lower()
                    return Command(
                        intent=CommandIntent.SEARCH,
                        action="search",
                        target=t_app,
                        query=q,
                        parameters={"query": q, "app": t_app},
                        raw_text=original,
                        confidence=1.0,
                        source=source
                    )
                return Command(
                    intent=CommandIntent.SEARCH,
                    action="search",
                    query=raw_q,
                    parameters={"query": raw_q},
                    raw_text=original,
                    confidence=1.0,
                    source=source
                )

        # Play Query
        m_play = self._pattern_play.match(text)
        if m_play:
            query = m_play.group(1).strip()
            return Command(
                intent=CommandIntent.PLAY,
                action="play",
                query=query,
                parameters={"query": query},
                raw_text=original,
                confidence=1.0,
                source=source
            )

        # Media Controls
        if self._pattern_pause.match(text):
            return Command(
                intent=CommandIntent.MEDIA_CONTROL,
                action="pause",
                raw_text=original,
                confidence=1.0,
                source=source
            )
        if self._pattern_resume.match(text):
            return Command(
                intent=CommandIntent.MEDIA_CONTROL,
                action="resume",
                raw_text=original,
                confidence=1.0,
                source=source
            )
        if self._pattern_next.match(text):
            return Command(
                intent=CommandIntent.MEDIA_CONTROL,
                action="next",
                raw_text=original,
                confidence=1.0,
                source=source
            )
        if self._pattern_prev.match(text):
            return Command(
                intent=CommandIntent.MEDIA_CONTROL,
                action="previous",
                raw_text=original,
                confidence=1.0,
                source=source
            )
        if self._pattern_forward.match(text):
            return Command(
                intent=CommandIntent.MEDIA_CONTROL,
                action="forward",
                raw_text=original,
                confidence=1.0,
                source=source
            )
        if self._pattern_rewind.match(text):
            return Command(
                intent=CommandIntent.MEDIA_CONTROL,
                action="rewind",
                raw_text=original,
                confidence=1.0,
                source=source
            )

        # Volume Controls
        m_vup = self._pattern_volume_up.match(text)
        if m_vup:
            amt = int(m_vup.group(1)) if m_vup.group(1) else 10
            return Command(
                intent=CommandIntent.VOLUME_CONTROL,
                action="volume_up",
                parameters={"amount": amt},
                raw_text=original,
                confidence=1.0,
                source=source
            )
        m_vdown = self._pattern_volume_down.match(text)
        if m_vdown:
            amt = int(m_vdown.group(1)) if m_vdown.group(1) else 10
            return Command(
                intent=CommandIntent.VOLUME_CONTROL,
                action="volume_down",
                parameters={"amount": amt},
                raw_text=original,
                confidence=1.0,
                source=source
            )
        if self._pattern_mute.match(text):
            return Command(
                intent=CommandIntent.VOLUME_CONTROL,
                action="mute",
                raw_text=original,
                confidence=1.0,
                source=source
            )

        # Specific Tab & Window Closes
        if self._pattern_close_youtube.match(text):
            return Command(
                intent=CommandIntent.CLOSE_YOUTUBE,
                action="close",
                target="youtube",
                raw_text=original,
                confidence=1.0,
                source=source
            )
        if self._pattern_close_instagram.match(text):
            return Command(
                intent=CommandIntent.CLOSE_INSTAGRAM,
                action="close",
                target="instagram",
                raw_text=original,
                confidence=1.0,
                source=source
            )
        if self._pattern_close_whatsapp.match(text):
            return Command(
                intent=CommandIntent.CLOSE_WHATSAPP,
                action="close",
                target="whatsapp",
                raw_text=original,
                confidence=1.0,
                source=source
            )
        if self._pattern_close_tab.match(text):
            return Command(
                intent=CommandIntent.CLOSE_TAB,
                action="close",
                target="tab",
                raw_text=original,
                confidence=1.0,
                source=source
            )
        if self._pattern_close_browser.match(text):
            return Command(
                intent=CommandIntent.CLOSE_BROWSER,
                action="close",
                target="browser",
                raw_text=original,
                confidence=1.0,
                source=source
            )

        # Specific Task Stops
        if self._pattern_stop_music.match(text):
            return Command(
                intent=CommandIntent.STOP_MUSIC,
                action="stop",
                target="music",
                raw_text=original,
                confidence=1.0,
                source=source
            )
        if self._pattern_stop_video.match(text):
            return Command(
                intent=CommandIntent.STOP_VIDEO,
                action="stop",
                target="video",
                raw_text=original,
                confidence=1.0,
                source=source
            )
        if self._pattern_stop_scroll.match(text):
            return Command(
                intent=CommandIntent.STOP_SCROLLING,
                action="stop",
                target="scrolling",
                raw_text=original,
                confidence=1.0,
                source=source
            )

        # Exit / Shutdown
        if self._pattern_exit.match(text):
            return Command(
                intent=CommandIntent.EXIT,
                action="shutdown",
                raw_text=original,
                confidence=1.0,
                source=source
            )

        # Diagnostics
        if self._pattern_diagnostics.match(text):
            return Command(
                intent=CommandIntent.DIAGNOSTICS,
                action="run",
                raw_text=original,
                confidence=1.0,
                source=source
            )

        # Gesture Mode
        if self._pattern_gesture_mode_start.match(text):
            return Command(
                intent=CommandIntent.GESTURE_MODE,
                action="start",
                raw_text=original,
                confidence=1.0,
                source=source
            )
        if self._pattern_gesture_mode_stop.match(text):
            return Command(
                intent=CommandIntent.GESTURE_MODE,
                action="stop",
                raw_text=original,
                confidence=1.0,
                source=source
            )

        return None

    def _match_fuzzy(self, text: str, original: str, source: str) -> Optional[Command]:
        """Perform difflib ratio comparison against known canonical voice anchors."""
        matches = difflib.get_close_matches(
            text,
            self.CANONICAL_PHRASES.keys(),
            n=1,
            cutoff=getattr(config, "FUZZY_MATCH_CUTOFF", 0.75)
        )
        if matches:
            best_match = matches[0]
            ratio = difflib.SequenceMatcher(None, text, best_match).ratio()
            intent, action, target = self.CANONICAL_PHRASES[best_match]
            logger.info(f"Fuzzy matched '{text}' -> '{best_match}' (Ratio: {ratio:.2f})")
            return Command(
                intent=intent,
                action=action,
                target=target,
                raw_text=original,
                confidence=round(ratio, 2),
                source=source
            )
        return None
