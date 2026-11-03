"""
actions/browser_actions.py - Browser and Web Automation Actions for SYRAX
Handles opening websites, web queries, and YouTube video stream lookups.
"""

import urllib.parse
import webbrowser
from typing import Optional, Tuple

import config
from core.browser_manager import get_browser_manager
from core.logger import get_logger

logger = get_logger("BrowserActions")


class BrowserActions:
    """Manages web browsing, Google search, and YouTube query navigation."""

    @staticmethod
    def open_url(url: str, app_key: Optional[str] = None) -> Tuple[bool, str]:
        """
        Open an arbitrary web URL in the managed browser (CDP primary, standard browser fallback).
        """
        try:
            if not url.startswith(("http://", "https://")):
                url = "https://" + url

            bm = get_browser_manager()
            try:
                opened, page, reason = bm.open_tab(url, app_key=app_key)
                if opened:
                    logger.info(f"Opened URL via BrowserManager CDP: {url}")
                    return True, f"Opened {url}"
            except Exception as cdp_err:
                logger.debug(f"CDP tab opening failed, falling back: {cdp_err}")

            logger.info(f"Opening URL via OS browser fallback: {url}")
            webbrowser.open_new_tab(url)
            return True, f"Opened {url}"
        except Exception as exc:
            logger.error(f"Failed to open URL '{url}': {exc}", exc_info=True)
            return False, f"Could not open browser: {exc}"

    @classmethod
    def open_site(cls, site_name: str) -> Tuple[bool, str]:
        """Open a recognized site key from config.QUICK_SITES."""
        key = site_name.strip().lower()
        url = config.QUICK_SITES.get(key)
        if url:
            return cls.open_url(url, app_key=key)
        # Fallback to .com domain
        fallback_url = f"https://www.{key}.com"
        return cls.open_url(fallback_url, app_key=key)

    @classmethod
    def search_google(cls, query: str) -> Tuple[bool, str]:
        """Perform a Google web search for the query."""
        if not query or not query.strip():
            return False, "Search query was empty."
        encoded = urllib.parse.quote_plus(query.strip())
        target_url = f"https://www.google.com/search?q={encoded}"
        logger.info(f"Executing Google search for '{query}'")
        return cls.open_url(target_url, app_key="google")

    @classmethod
    def play_youtube(cls, query: str) -> Tuple[bool, str]:
        """Search and prepare playback for a video on YouTube."""
        if not query or not query.strip():
            return cls.open_site("youtube")
        encoded = urllib.parse.quote_plus(query.strip())
        target_url = f"https://www.youtube.com/results?search_query={encoded}"
        logger.info(f"Searching YouTube for '{query}'")
        return cls.open_url(target_url, app_key="youtube")

    @classmethod
    def close_current_tab(cls, app_key: Optional[str] = None) -> Tuple[bool, str]:
        """Close SYRAX-opened browser tab."""
        bm = get_browser_manager()
        res = bm.close_tab(app_key=app_key)
        return res.success, res.reason

    @classmethod
    def close_all_browser(cls) -> Tuple[bool, str]:
        """Close SYRAX-managed browser instance."""
        bm = get_browser_manager()
        res = bm.close_browser()
        return res.success, res.reason
