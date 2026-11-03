"""
gesture/profiles.py - Dynamic Application-Specific Gesture Profiles for SYRAX
Selects gesture mappings based on foreground window process and title patterns.
Strictly isolates mappings between apps, enforces hardcoded safety deny-lists
(e.g., WhatsApp can NEVER map Enter/Return/Send to any gesture), and supports manual overrides.
"""

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("GestureProfiles")

DEFAULT_PROFILES_FILE = "config/app_profiles.json"

# Strict safety deny-list: these actions can NEVER be executed via gestures in WhatsApp
WHATSAPP_FORBIDDEN_KEYS = {"enter", "return", "click_send", "\n", "\r"}


@dataclass
class GestureActionConfig:
    """Configuration for an individual gesture action."""
    action_type: str                  # "key", "hotkey", "scroll", "system"
    keys: List[str] = field(default_factory=list)
    direction: Optional[str] = None   # "up" or "down" (for scrolling)
    command: Optional[str] = None     # "pause_actions"
    cooldown_ms: int = 600
    description: str = ""


@dataclass
class AppProfile:
    """Full mapping profile for an application."""
    key: str
    name: str
    process_names: List[str]
    title_keywords: List[str]
    actions: Dict[str, GestureActionConfig]
    denied_keys: List[str] = field(default_factory=list)


class ProfileManager:
    """
    Loads, manages, and resolves application profiles.
    Evaluates foreground window process/title at the moment of gesture execution.
    """

    def __init__(self, profiles_path: str = DEFAULT_PROFILES_FILE) -> None:
        self.profiles_path = profiles_path
        self.profiles: Dict[str, AppProfile] = {}
        self.manual_override_profile: Optional[str] = None

        self._load_profiles()

    def _load_profiles(self) -> None:
        """Parse profiles from config/app_profiles.json."""
        if not os.path.exists(self.profiles_path):
            logger.warning(f"Profiles file not found at {self.profiles_path}. Using internal defaults.")
            self._init_fallback_profiles()
            return

        try:
            with open(self.profiles_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            for key, pdata in data.get("profiles", {}).items():
                actions_map: Dict[str, GestureActionConfig] = {}
                for g_name, a_info in pdata.get("actions", {}).items():
                    actions_map[g_name] = GestureActionConfig(
                        action_type=a_info.get("action_type", "key"),
                        keys=a_info.get("keys", []),
                        direction=a_info.get("direction"),
                        command=a_info.get("command"),
                        cooldown_ms=a_info.get("cooldown_ms", 600),
                        description=a_info.get("description", "")
                    )

                self.profiles[key] = AppProfile(
                    key=key,
                    name=pdata.get("name", key.capitalize()),
                    process_names=[p.lower() for p in pdata.get("process_names", [])],
                    title_keywords=[t.lower() for t in pdata.get("title_keywords", [])],
                    actions=actions_map,
                    denied_keys=[k.lower() for k in pdata.get("denied_keys", [])]
                )
            logger.info(f"Loaded {len(self.profiles)} gesture profiles: {list(self.profiles.keys())}")
        except Exception as exc:
            logger.error(f"Error loading {self.profiles_path}: {exc}. Using fallback profiles.")
            self._init_fallback_profiles()

    def _init_fallback_profiles(self) -> None:
        """In-memory default profiles if file is missing."""
        self.profiles = {
            "youtube": AppProfile(
                key="youtube",
                name="YouTube",
                process_names=["chrome.exe", "msedge.exe", "firefox.exe"],
                title_keywords=["youtube"],
                actions={
                    "OPEN_PALM": GestureActionConfig("key", ["k"], description="Play / Pause"),
                    "TWO_FINGERS_RIGHT": GestureActionConfig("key", ["l"], description="Forward 10s"),
                    "TWO_FINGERS_LEFT": GestureActionConfig("key", ["j"], description="Rewind 10s"),
                    "SWIPE_RIGHT": GestureActionConfig("hotkey", ["shift", "n"], description="Next Video"),
                    "SWIPE_LEFT": GestureActionConfig("hotkey", ["shift", "p"], description="Previous Video"),
                    "ONE_FINGER_UP": GestureActionConfig("scroll", direction="up", description="Scroll Up"),
                    "ONE_FINGER_DOWN": GestureActionConfig("scroll", direction="down", description="Scroll Down"),
                    "PINCH_OUT": GestureActionConfig("hotkey", ["ctrl", "="], description="Zoom In"),
                    "PINCH_IN": GestureActionConfig("hotkey", ["ctrl", "-"], description="Zoom Out"),
                }
            ),
            "whatsapp": AppProfile(
                key="whatsapp",
                name="WhatsApp Desktop",
                process_names=["whatsapp.exe", "whatsappdesktop.exe"],
                title_keywords=["whatsapp"],
                actions={
                    "ONE_FINGER_UP": GestureActionConfig("scroll", direction="up", description="Scroll Up"),
                    "ONE_FINGER_DOWN": GestureActionConfig("scroll", direction="down", description="Scroll Down"),
                    "OPEN_PALM": GestureActionConfig("system", command="pause_actions", description="Pause Actions"),
                },
                denied_keys=["enter", "return", "click_send"]
            ),
            "default": AppProfile(
                key="default",
                name="Default App",
                process_names=[],
                title_keywords=[],
                actions={
                    "ONE_FINGER_UP": GestureActionConfig("scroll", direction="up", description="Scroll Up"),
                    "ONE_FINGER_DOWN": GestureActionConfig("scroll", direction="down", description="Scroll Down"),
                }
            )
        }

    def set_manual_override(self, profile_key: Optional[str]) -> None:
        """Manually lock active profile from dashboard or voice."""
        if profile_key and profile_key.lower() in self.profiles:
            self.manual_override_profile = profile_key.lower()
            logger.info(f"Manual profile override set to: {self.manual_override_profile}")
        else:
            self.manual_override_profile = None
            logger.info("Cleared manual profile override. Reverting to automatic detection.")

    def resolve_profile(self, process_name: str, window_title: str) -> AppProfile:
        """
        Determine active profile for the currently focused foreground window.
        Respects manual override if set.
        """
        if self.manual_override_profile and self.manual_override_profile in self.profiles:
            return self.profiles[self.manual_override_profile]

        proc = process_name.lower().strip()
        title = window_title.lower().strip()

        # Check WhatsApp first
        if "whatsapp" in proc or "whatsapp" in title:
            return self.profiles.get("whatsapp", self.profiles["default"])

        # Check YouTube
        if "youtube" in title or (any(b in proc for b in ("chrome", "edge", "firefox", "brave", "opera")) and "youtube" in title):
            return self.profiles.get("youtube", self.profiles["default"])

        # Check Instagram
        if "instagram" in title or "reels" in title:
            return self.profiles.get("instagram", self.profiles["default"])

        # Check Presentation
        if any(p in proc for p in ("powerpnt", "impress", "soffice")) or any(k in title for k in ("slides", "presentation", "powerpoint")):
            return self.profiles.get("presentation", self.profiles["default"])

        # Default fallback
        return self.profiles.get("default", AppProfile("default", "Default", [], [], {}))

    def get_action_for_gesture(
        self,
        profile: AppProfile,
        gesture_name: str
    ) -> Optional[GestureActionConfig]:
        """
        Retrieve action config for gesture within specified profile.
        Strictly enforces WhatsApp and general deny-lists.
        """
        action = profile.actions.get(gesture_name)
        if not action:
            return None

        # Hardcoded WhatsApp safety check:
        if profile.key == "whatsapp":
            # WhatsApp can never execute enter, return, or send
            for key in action.keys:
                if key.lower() in WHATSAPP_FORBIDDEN_KEYS:
                    logger.critical(
                        f"SAFETY BLOCK: Prevented forbidden key '{key}' from executing in WhatsApp profile!"
                    )
                    return None

        # Check profile-level denied keys
        for key in action.keys:
            if key.lower() in profile.denied_keys:
                logger.warning(f"Action key '{key}' is denied in profile '{profile.name}'")
                return None

        return action
