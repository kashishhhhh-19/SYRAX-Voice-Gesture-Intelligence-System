"""
actions/youtube_actions.py - YouTube Search, Evaluation, Focus & Playback for SYRAX
Implements song title and artist ranking, candidate scoring, automated playback launch,
and synchronized playback controls through FocusManager.
"""

import json
import re
import threading
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import List, Optional, Tuple

import config
import pyautogui
from actions.focus_manager import get_focus_manager
from core.browser_manager import get_browser_manager
from core.conversation_state import get_conversation_state
from core.event_bus import Events, get_event_bus
from core.logger import get_logger

logger = get_logger("YouTubeActions")


@dataclass
class YouTubeCandidate:
    """Represents a candidate YouTube video extracted from search results."""
    video_id: str
    title: str
    channel: str
    is_official: bool = False
    is_topic: bool = False
    view_count_text: str = ""
    score: float = 0.0


def score_candidate(
    candidate: YouTubeCandidate,
    song_title: Optional[str] = None,
    artist: Optional[str] = None,
    preferred_query: Optional[str] = None
) -> float:
    """
    Pure heuristic scoring function to rank candidate YouTube videos.
    Prioritizes official releases, artist channel matches, and exact title matches
    over covers, 1-hour loops, and amateur remixes.
    """
    score = 0.0
    title_lower = candidate.title.lower()
    channel_lower = candidate.channel.lower()

    # 1. Song title match (Up to +35 pts)
    if song_title:
        clean_song = song_title.lower().strip()
        if clean_song in title_lower:
            score += 35.0
        else:
            # Token overlap
            tokens = [t for t in clean_song.split() if len(t) > 2]
            if tokens:
                matched_tokens = sum(1 for t in tokens if t in title_lower)
                score += (matched_tokens / len(tokens)) * 25.0

    # 2. Artist match in channel or title (Up to +35 pts)
    if artist:
        clean_artist = artist.lower().strip()
        if clean_artist in channel_lower:
            score += 35.0
        elif clean_artist in title_lower:
            score += 20.0
        else:
            tokens = [t for t in clean_artist.split() if len(t) > 2]
            if tokens:
                matched_tokens = sum(1 for t in tokens if t in channel_lower or t in title_lower)
                score += (matched_tokens / len(tokens)) * 18.0

    # 3. Official / Topic channel bonus (+25 pts)
    if candidate.is_official or "vevo" in channel_lower or "official" in channel_lower:
        score += 25.0
    if candidate.is_topic or "- topic" in channel_lower:
        score += 20.0
    if any(k in title_lower for k in ("official video", "official audio", "music video", "official music video")):
        score += 15.0

    # 4. Query term match fallback if no explicit song/artist
    if not song_title and not artist and preferred_query:
        q_tokens = [t for t in preferred_query.lower().split() if len(t) > 2]
        if q_tokens:
            matches = sum(1 for t in q_tokens if t in title_lower or t in channel_lower)
            score += (matches / len(q_tokens)) * 40.0

    # 5. Penalties for undesirable content (-25 pts each)
    penalties = ["1 hour", "10 hours", "loop", "extended", "8d audio", "bass boosted", "slowed", "reverb", "karaoke", "instrumental"]
    for pen in penalties:
        # Only penalize if user didn't ask for it
        if pen in title_lower and (not preferred_query or pen not in preferred_query.lower()):
            score -= 25.0

    candidate.score = round(score, 2)
    return candidate.score


class YouTubeActions:
    """
    Coordinates YouTube search, video scoring, window foregrounding,
    playback launch, and keyboard shortcut execution.
    """

    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )

    def __init__(self, focus_manager=None, browser_manager=None, conversation_state=None) -> None:
        self.focus_manager = focus_manager or get_focus_manager()
        self.browser_manager = browser_manager or get_browser_manager()
        self.conversation_state = conversation_state or get_conversation_state()
        self._event_bus = get_event_bus()

    def search_candidates(self, query: str, timeout: float = 3.0) -> List[YouTubeCandidate]:
        """
        Query YouTube search results and parse candidate video metadata.
        Uses pure regex/JSON parsing on initial response without heavy browser dependencies.
        """
        if not query or not query.strip():
            return []

        clean_query = query.strip()
        encoded = urllib.parse.quote_plus(clean_query)
        search_url = f"https://www.youtube.com/results?search_query={encoded}"

        candidates: List[YouTubeCandidate] = []
        try:
            req = urllib.request.Request(
                search_url,
                headers={"User-Agent": self.USER_AGENT, "Accept-Language": "en-US,en;q=0.9"}
            )
            with urllib.request.urlopen(req, timeout=timeout) as response:
                html = response.read().decode("utf-8", errors="replace")

            # Extract initial data JSON
            json_match = re.search(r"var ytInitialData\s*=\s*({.+?});</script>", html)
            if json_match:
                try:
                    data = json.loads(json_match.group(1))
                    sections = (
                        data.get("contents", {})
                        .get("twoColumnSearchResultsRenderer", {})
                        .get("primaryContents", {})
                        .get("sectionListRenderer", {})
                        .get("contents", [])
                    )
                    for sec in sections:
                        items = sec.get("itemSectionRenderer", {}).get("contents", [])
                        for it in items:
                            v_data = it.get("videoRenderer")
                            if not v_data:
                                continue

                            vid = v_data.get("videoId")
                            title_runs = v_data.get("title", {}).get("runs", [])
                            title = "".join(r.get("text", "") for r in title_runs)
                            owner_runs = v_data.get("ownerText", {}).get("runs", [])
                            channel = "".join(r.get("text", "") for r in owner_runs)

                            # Badges
                            badges = v_data.get("ownerBadges", [])
                            is_official = any("OFFICIAL" in str(b) or "VERIFIED" in str(b) for b in badges)
                            is_topic = "- Topic" in channel

                            views = v_data.get("viewCountText", {}).get("simpleText", "")

                            if vid and title:
                                candidates.append(
                                    YouTubeCandidate(
                                        video_id=vid,
                                        title=title,
                                        channel=channel,
                                        is_official=is_official,
                                        is_topic=is_topic,
                                        view_count_text=views
                                    )
                                )
                                if len(candidates) >= 8:
                                    break
                        if len(candidates) >= 8:
                            break
                except Exception as parse_err:
                    logger.debug(f"JSON initial data parse error: {parse_err}")

            # Fallback regex search if initial data was structured differently
            if not candidates:
                raw_ids = re.findall(r"/watch\?v=([a-zA-Z0-9_-]{11})", html)
                seen = set()
                for vid in raw_ids:
                    if vid not in seen:
                        seen.add(vid)
                        candidates.append(
                            YouTubeCandidate(
                                video_id=vid,
                                title=query,
                                channel="YouTube",
                                is_official=False
                            )
                        )
                    if len(candidates) >= 5:
                        break

        except Exception as net_err:
            logger.warning(f"YouTube candidate search encountered network error: {net_err}")

        return candidates

    def play_best_match(
        self,
        query: str,
        song_title: Optional[str] = None,
        artist: Optional[str] = None,
        cancellation_token: Optional[threading.Event] = None,
        wait_time: float = 0.5
    ) -> Tuple[bool, str, str]:
        """
        Main entry point for 'SYRAX, play Barsaat by Banjare'.
        Searches, scores candidates, launches top video, focuses browser, and returns spoken response.
        Uses BrowserManager CDP as primary verifiable layer, with FocusManager as fallback.
        """
        import webbrowser

        if cancellation_token and cancellation_token.is_set():
            return False, "Cancelled", "Operation was cancelled."

        # 1. Search candidates
        search_term = f"{song_title} {artist}" if song_title and artist else query
        logger.info(f"Searching YouTube candidates for: '{search_term}'")
        candidates = self.search_candidates(search_term)

        if cancellation_token and cancellation_token.is_set():
            return False, "Cancelled", "Operation was cancelled."

        target_url: str
        spoken_response: str
        chosen_title = song_title or query

        if candidates:
            # Score each candidate
            for cand in candidates:
                score_candidate(cand, song_title=song_title, artist=artist, preferred_query=query)

            candidates.sort(key=lambda c: c.score, reverse=True)
            winner = candidates[0]
            logger.info(f"Top scored YouTube video: '{winner.title}' by '{winner.channel}' (Score: {winner.score})")

            target_url = f"https://www.youtube.com/watch?v={winner.video_id}"
            if song_title and artist:
                spoken_response = f"Playing {song_title} by {artist} on YouTube."
            elif song_title:
                spoken_response = f"Playing {song_title} on YouTube."
            else:
                spoken_response = f"Playing {winner.title} on YouTube."
        else:
            # Fallback to direct search results page
            logger.info(f"No candidates extracted. Launching direct search results for '{search_term}'")
            encoded = urllib.parse.quote_plus(search_term)
            target_url = f"https://www.youtube.com/results?search_query={encoded}"
            if song_title and artist:
                spoken_response = f"Playing {song_title} by {artist} on YouTube."
            else:
                spoken_response = f"Searching YouTube for {query}."

        if cancellation_token and cancellation_token.is_set():
            return False, "Cancelled", "Operation was cancelled."

        # Update conversational state
        self.conversation_state.last_video_query = chosen_title
        self.conversation_state.touch()

        # 2. Launch in browser (Primary: BrowserManager CDP)
        launched_via_cdp = False
        try:
            opened, page, reason = self.browser_manager.open_tab(target_url, app_key="youtube")
            if opened:
                launched_via_cdp = True
                logger.info(f"Launched YouTube via BrowserManager CDP: {reason}")
                # Wait briefly and verify playback via DOM
                time.sleep(0.5)
                self.browser_manager.evaluate_js(
                    "youtube",
                    "(() => { const v = document.querySelector('video'); if (v) { v.play().catch(() => {}); return !v.paused; } return false; })()"
                )
        except Exception as cdp_err:
            logger.debug(f"CDP tab launch failed or unavailable, falling back: {cdp_err}")

        if not launched_via_cdp:
            # Fallback: OS standard browser
            try:
                webbrowser.open_new_tab(target_url)
            except Exception as open_err:
                logger.error(f"Failed to open browser tab for YouTube: {open_err}")
                return False, f"Failed to open browser: {open_err}", "Could not open browser."

            # 3. Wait briefly for browser tab to initialize
            if wait_time > 0:
                steps = int(wait_time / 0.1)
                for _ in range(max(1, steps)):
                    if cancellation_token and cancellation_token.is_set():
                        return False, "Cancelled", "Operation was cancelled."
                    time.sleep(0.1)

            # 4. Attempt to focus YouTube window
            try:
                self.focus_manager.ensure_youtube_focused(needs_player_click=True)
            except Exception as focus_err:
                logger.debug(f"Focus attempt after launch: {focus_err}")

        # Notify UI
        self._event_bus.emit(
            Events.ACTIVITY_LOG,
            category="MEDIA",
            message=f"YouTube playback active: {chosen_title}"
        )

        return True, f"Launched {target_url}", spoken_response

    # =========================================================================
    # Playback Controls (Verifiable CDP Primary, FocusManager Fallback)
    # =========================================================================

    def play_pause(self) -> Tuple[bool, str]:
        """Toggle video play/pause with DOM verification; falls back to 'k' key."""
        # 1. Primary CDP Check
        if self.browser_manager.is_connected() and self.browser_manager.get_tab("youtube"):
            res = self.browser_manager.evaluate_js(
                "youtube",
                "(() => { const v = document.querySelector('video'); if (!v) return {found: false}; if (v.paused) { v.play().catch(() => {}); } else { v.pause(); } return {found: true, paused: v.paused}; })()"
            )
            if res.success and isinstance(res.data, dict) and res.data.get("found"):
                is_paused = res.data.get("paused")
                state = "paused" if is_paused else "resumed"
                return True, f"YouTube playback {state} (DOM verified)"

        # 2. FocusManager Shortcut Fallback
        return self.focus_manager.execute_youtube_action(
            lambda: (pyautogui.press("k") is None and (True, "Playback toggled (k)"))
        )

    def pause(self) -> Tuple[bool, str]:
        """Explicitly pause video playback with DOM verification."""
        if self.browser_manager.is_connected() and self.browser_manager.get_tab("youtube"):
            res = self.browser_manager.evaluate_js(
                "youtube",
                "(() => { const v = document.querySelector('video'); if (!v) return {found: false}; v.pause(); return {found: true, paused: v.paused}; })()"
            )
            if res.success and isinstance(res.data, dict) and res.data.get("found"):
                return True, "YouTube video paused (DOM verified)"

        return self.focus_manager.execute_youtube_action(
            lambda: (pyautogui.press("k") is None and (True, "Video paused (k)"))
        )

    def resume(self) -> Tuple[bool, str]:
        """Explicitly resume video playback with DOM verification."""
        if self.browser_manager.is_connected() and self.browser_manager.get_tab("youtube"):
            res = self.browser_manager.evaluate_js(
                "youtube",
                "(() => { const v = document.querySelector('video'); if (!v) return {found: false}; v.play().catch(() => {}); return {found: true, paused: v.paused}; })()"
            )
            if res.success and isinstance(res.data, dict) and res.data.get("found"):
                return True, "YouTube video resumed (DOM verified)"

        return self.focus_manager.execute_youtube_action(
            lambda: (pyautogui.press("k") is None and (True, "Video resumed (k)"))
        )

    def next_video(self) -> Tuple[bool, str]:
        """Skip to next video with Shift+N or DOM next button."""
        if self.browser_manager.is_connected() and self.browser_manager.get_tab("youtube"):
            res = self.browser_manager.evaluate_js(
                "youtube",
                "(() => { const btn = document.querySelector('a.ytp-next-button'); if (btn) { btn.click(); return true; } return false; })()"
            )
            if res.success and res.data:
                return True, "Skipped to next video (DOM verified)"

        def _action():
            pyautogui.hotkey("shift", "n")
            return True, "Skipped to next video (Shift+N)"
        return self.focus_manager.execute_youtube_action(_action)

    def previous_video(self) -> Tuple[bool, str]:
        """Return to previous video with Shift+P, or fallback to browser back."""
        if self.browser_manager.is_connected() and self.browser_manager.get_tab("youtube"):
            res = self.browser_manager.evaluate_js(
                "youtube",
                "(() => { const btn = document.querySelector('a.ytp-prev-button'); if (btn) { btn.click(); return true; } window.history.back(); return true; })()"
            )
            if res.success and res.data:
                return True, "Previous video (DOM verified)"

        def _action():
            pyautogui.hotkey("shift", "p")
            return True, "Previous video (Shift+P)"
        return self.focus_manager.execute_youtube_action(_action)

    def forward(self, seconds: int = 10) -> Tuple[bool, str]:
        """Seek forward 10 seconds with DOM manipulation or 'l' key."""
        if self.browser_manager.is_connected() and self.browser_manager.get_tab("youtube"):
            res = self.browser_manager.evaluate_js(
                "youtube",
                f"(() => {{ const v = document.querySelector('video'); if (v) {{ v.currentTime += {seconds}; return true; }} return false; }})()"
            )
            if res.success and res.data:
                return True, f"Forward {seconds}s (DOM verified)"

        def _action():
            pyautogui.press("l")
            return True, f"Forward {seconds}s (l)"
        return self.focus_manager.execute_youtube_action(_action)

    def rewind(self, seconds: int = 10) -> Tuple[bool, str]:
        """Seek backward 10 seconds with DOM manipulation or 'j' key."""
        if self.browser_manager.is_connected() and self.browser_manager.get_tab("youtube"):
            res = self.browser_manager.evaluate_js(
                "youtube",
                f"(() => {{ const v = document.querySelector('video'); if (v) {{ v.currentTime -= {seconds}; return true; }} return false; }})()"
            )
            if res.success and res.data:
                return True, f"Rewind {seconds}s (DOM verified)"

        def _action():
            pyautogui.press("j")
            return True, f"Rewind {seconds}s (j)"
        return self.focus_manager.execute_youtube_action(_action)

    def close_youtube(self) -> Tuple[bool, str]:
        """Close SYRAX-opened YouTube tab via BrowserManager."""
        res = self.browser_manager.close_tab("youtube")
        if res.success:
            return True, res.reason

        # Fallback to FocusManager if YouTube window is currently in foreground
        def _close():
            pyautogui.hotkey("ctrl", "w")
            return True, "Closed YouTube window via shortcut"
        return self.focus_manager.execute_youtube_action(_close, needs_player_click=False)

    def scroll_down(self) -> Tuple[bool, str]:
        """Scroll page down."""
        if self.browser_manager.is_connected() and self.browser_manager.get_tab("youtube"):
            res = self.browser_manager.evaluate_js("youtube", "window.scrollBy(0, 300); true;")
            if res.success:
                return True, "Scrolled down (DOM verified)"

        def _action():
            pyautogui.scroll(-config.SCROLL_STEP)
            return True, "Scrolled down"
        return self.focus_manager.execute_youtube_action(_action, needs_player_click=False)

    def scroll_up(self) -> Tuple[bool, str]:
        """Scroll page up."""
        if self.browser_manager.is_connected() and self.browser_manager.get_tab("youtube"):
            res = self.browser_manager.evaluate_js("youtube", "window.scrollBy(0, -300); true;")
            if res.success:
                return True, "Scrolled up (DOM verified)"

        def _action():
            pyautogui.scroll(config.SCROLL_STEP)
            return True, "Scrolled up"
        return self.focus_manager.execute_youtube_action(_action, needs_player_click=False)

    def zoom_in(self) -> Tuple[bool, str]:
        """Zoom in (Ctrl + plus)."""
        def _action():
            pyautogui.hotkey("ctrl", "+")
            return True, "Zoomed in"
        return self.focus_manager.execute_youtube_action(_action, needs_player_click=False)

    def zoom_out(self) -> Tuple[bool, str]:
        """Zoom out (Ctrl + minus)."""
        def _action():
            pyautogui.hotkey("ctrl", "-")
            return True, "Zoomed out"
        return self.focus_manager.execute_youtube_action(_action, needs_player_click=False)


# Global singleton
_global_youtube_actions: Optional[YouTubeActions] = None


def get_youtube_actions() -> YouTubeActions:
    """Retrieve the global YouTubeActions singleton."""
    global _global_youtube_actions
    if _global_youtube_actions is None:
        _global_youtube_actions = YouTubeActions()
    return _global_youtube_actions
