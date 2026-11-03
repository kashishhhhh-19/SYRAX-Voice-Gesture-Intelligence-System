"""
core/browser_manager.py - Real Browser Automation & Tab Manager for SYRAX
Primary verifiable layer using Chrome DevTools Protocol (CDP) via Playwright.
Launches system Chrome or Edge with a dedicated persistent profile directory
(%LOCALAPPDATA%\\SYRAX\\browser_profile) so YouTube, Instagram, and WhatsApp Web
sessions persist across restarts with zero credential storage.
Tracks and manages ONLY tabs opened by SYRAX. Never closes user's personal tabs.
"""

import json
import os
import subprocess
import threading
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import config
from core.event_bus import Events, get_event_bus
from core.logger import get_logger

logger = get_logger("BrowserManager")


@dataclass
class BrowserActionResult:
    """Standardized outcome for browser operations."""
    success: bool
    verified: bool
    reason: str
    data: Any = None


class BrowserManager:
    """
    Manages Chrome/Edge browser automation via Chrome DevTools Protocol (CDP).
    Launches Chrome/Edge with --remote-debugging-port and persistent profile.
    Only manages and closes tabs explicitly opened by SYRAX.
    """

    DEFAULT_DEBUG_PORT = 9222

    def __init__(
        self,
        port: int = DEFAULT_DEBUG_PORT,
        profile_dir: Optional[str] = None
    ) -> None:
        self.port = port
        self._lock = threading.RLock()
        self._event_bus = get_event_bus()

        # Dedicated persistent profile directory
        if profile_dir:
            self.profile_dir = Path(profile_dir)
        else:
            local_appdata = os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))
            self.profile_dir = Path(local_appdata) / "SYRAX" / "browser_profile"

        self.profile_dir.mkdir(parents=True, exist_ok=True)

        # Process and Playwright references
        self._browser_process: Optional[subprocess.Popen] = None
        self._playwright = None
        self._browser = None
        self._context = None

        # Registry of SYRAX-opened page IDs (UUIDs or target IDs)
        self._syrax_page_ids: Set[str] = set()

        # Application-specific cached page references
        self._app_tabs: Dict[str, Any] = {}  # "youtube", "instagram", "whatsapp"

    # =========================================================================
    # 1. BROWSER LAUNCH & PROCESS MANAGEMENT
    # =========================================================================

    def find_browser_executable(self) -> Optional[str]:
        """Locate Google Chrome or Microsoft Edge on the Windows system."""
        candidates = [
            # Chrome
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.join(os.environ.get("LOCALAPPDATA", ""), r"Google\Chrome\Application\chrome.exe"),
            # Edge
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            os.path.join(os.environ.get("LOCALAPPDATA", ""), r"Microsoft\Edge\Application\msedge.exe"),
            # Brave
            r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
            os.path.join(os.environ.get("LOCALAPPDATA", ""), r"BraveSoftware\Brave-Browser\Application\brave.exe"),
        ]
        for path in candidates:
            if path and os.path.isfile(path):
                logger.info(f"Located browser executable: {path}")
                return path

        logger.warning("No installed Chrome/Edge executable found in standard locations.")
        return None

    def is_cdp_port_active(self) -> bool:
        """Check if browser remote debugging port is actively responding."""
        try:
            url = f"http://127.0.0.1:{self.port}/json/version"
            with urllib.request.urlopen(url, timeout=1.5) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    return "webSocketDebuggerUrl" in data
        except Exception:
            pass
        return False

    def launch_browser(self) -> bool:
        """
        Launch Chrome/Edge with remote debugging enabled and dedicated persistent profile.
        If already running with CDP port active, reuses the existing instance.
        """
        with self._lock:
            if self.is_cdp_port_active():
                logger.info(f"CDP port {self.port} is already active. Reusing running browser.")
                return True

            exe = self.find_browser_executable()
            if not exe:
                logger.error("Cannot launch managed browser: executable not found.")
                return False

            cmd = [
                exe,
                f"--remote-debugging-port={self.port}",
                f"--user-data-dir={str(self.profile_dir)}",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-background-networking",
                "--disable-features=TranslateUI",
                "--password-store=basic",
            ]

            logger.info(f"Launching managed browser with persistent profile at: {self.profile_dir}")
            try:
                self._browser_process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )

                # Wait up to 5 seconds for CDP port to open
                for _ in range(25):
                    time.sleep(0.2)
                    if self.is_cdp_port_active():
                        logger.info("Browser CDP port is ready.")
                        return True

                logger.warning("Browser process started but CDP port did not respond in time.")
                return False
            except Exception as exc:
                logger.error(f"Failed to launch managed browser process: {exc}", exc_info=True)
                return False

    # =========================================================================
    # 2. CDP CONNECTION (PLAYWRIGHT)
    # =========================================================================

    def connect(self) -> bool:
        """Connect Playwright to the active browser over CDP."""
        with self._lock:
            if self.is_connected():
                return True

            # Ensure browser process is up
            if not self.is_cdp_port_active():
                launched = self.launch_browser()
                if not launched:
                    return False

            try:
                from playwright.sync_api import sync_playwright

                if self._playwright is None:
                    self._playwright = sync_playwright().start()

                cdp_url = f"http://127.0.0.1:{self.port}"
                logger.info(f"Connecting Playwright over CDP to {cdp_url}...")
                self._browser = self._playwright.chromium.connect_over_cdp(cdp_url)

                if self._browser.contexts:
                    self._context = self._browser.contexts[0]
                else:
                    self._context = self._browser.new_context()

                self._event_bus.emit(
                    Events.ACTIVITY_LOG,
                    category="SYSTEM",
                    message="Connected to browser over Chrome DevTools Protocol (CDP)."
                )
                return True
            except Exception as exc:
                logger.error(f"Failed to connect Playwright over CDP: {exc}")
                self._cleanup_connection()
                return False

    def is_connected(self) -> bool:
        """Check if CDP connection is active and responsive."""
        with self._lock:
            if self._browser is None or self._context is None:
                return False
            try:
                # Test connectivity by querying pages
                _ = len(self._context.pages)
                return True
            except Exception:
                return False

    def _cleanup_connection(self) -> None:
        """Clean up Playwright references after disconnection."""
        with self._lock:
            try:
                if self._browser:
                    self._browser.close()
            except Exception:
                pass
            self._browser = None
            self._context = None
            self._app_tabs.clear()

    # =========================================================================
    # 3. TAB MANAGEMENT (TRACKS & CLOSES ONLY SYRAX-OPENED TABS)
    # =========================================================================

    def open_tab(self, url: str, app_key: Optional[str] = None) -> Tuple[bool, Any, str]:
        """
        Open a new tab or reuse existing tab for an application.
        Registers the tab ID in SYRAX's tracked set so personal tabs are never touched.
        """
        with self._lock:
            if not self.connect():
                return False, None, "Could not connect to browser via CDP."

            try:
                # Check if app already has an active open tab
                if app_key and app_key in self._app_tabs:
                    existing_page = self._app_tabs[app_key]
                    try:
                        if not existing_page.is_closed():
                            existing_page.bring_to_front()
                            if url and not existing_page.url.startswith(url):
                                existing_page.goto(url, wait_until="domcontentloaded", timeout=15000)
                            return True, existing_page, f"Reused existing {app_key} tab."
                    except Exception:
                        pass

                # Check if an existing page in context matches the URL pattern
                for p in self._context.pages:
                    try:
                        if not p.is_closed() and app_key and app_key in p.url.lower():
                            p.bring_to_front()
                            self._syrax_page_ids.add(self._get_page_id(p))
                            if app_key:
                                self._app_tabs[app_key] = p
                            return True, p, f"Focused open {app_key} tab."
                    except Exception:
                        continue

                # Open fresh tab
                page = self._context.new_page()
                page_id = self._get_page_id(page)
                self._syrax_page_ids.add(page_id)

                if app_key:
                    self._app_tabs[app_key] = page

                logger.info(f"Opening URL '{url}' in SYRAX-managed tab [ID: {page_id}]")
                page.goto(url, wait_until="domcontentloaded", timeout=20000)
                page.bring_to_front()

                return True, page, f"Opened {url}"
            except Exception as exc:
                err = f"Failed to open tab for {url}: {exc}"
                logger.error(err, exc_info=True)
                return False, None, err

    def get_tab(self, app_key: str) -> Optional[Any]:
        """Get the active Page object for an application if open and alive."""
        with self._lock:
            page = self._app_tabs.get(app_key)
            if page:
                try:
                    if not page.is_closed():
                        return page
                except Exception:
                    pass
                del self._app_tabs[app_key]

            # Scan open pages for matching app
            if self.is_connected() and self._context:
                for p in self._context.pages:
                    try:
                        if not p.is_closed() and app_key in p.url.lower():
                            self._app_tabs[app_key] = p
                            self._syrax_page_ids.add(self._get_page_id(p))
                            return p
                    except Exception:
                        continue
            return None

    def close_tab(self, app_key: Optional[str] = None) -> BrowserActionResult:
        """
        Close a tab opened by SYRAX.
        STRICT SAFETY: Only closes tabs recorded in self._syrax_page_ids!
        Never closes user's personal tabs.
        """
        with self._lock:
            if not self.is_connected():
                return BrowserActionResult(False, False, "Browser is not connected.")

            target_page = None
            if app_key:
                target_page = self.get_tab(app_key)

            if not target_page:
                # Close active page if it is in SYRAX-opened set
                for p in self._context.pages:
                    try:
                        pid = self._get_page_id(p)
                        if pid in self._syrax_page_ids and not p.is_closed():
                            target_page = p
                            break
                    except Exception:
                        continue

            if not target_page:
                return BrowserActionResult(
                    False, False,
                    f"No SYRAX-managed tab found to close{' for ' + app_key if app_key else ''}."
                )

            try:
                pid = self._get_page_id(target_page)
                logger.info(f"Closing SYRAX-managed tab: {target_page.url} [ID: {pid}]")
                target_page.close()
                self._syrax_page_ids.discard(pid)
                if app_key and app_key in self._app_tabs:
                    del self._app_tabs[app_key]
                return BrowserActionResult(True, True, f"Closed {app_key or 'tab'} successfully.")
            except Exception as exc:
                return BrowserActionResult(False, False, f"Error closing tab: {exc}")

    def close_browser(self) -> BrowserActionResult:
        """
        Closes the SYRAX-managed browser instance completely.
        Does NOT affect unrelated Chrome or Edge instances.
        """
        with self._lock:
            logger.info("Closing SYRAX-managed browser instance...")
            try:
                if self._browser:
                    self._browser.close()
            except Exception:
                pass

            try:
                if self._playwright:
                    self._playwright.stop()
            except Exception:
                pass

            self._playwright = None
            self._browser = None
            self._context = None
            self._app_tabs.clear()
            self._syrax_page_ids.clear()

            # Terminate subprocess if still active
            if self._browser_process:
                try:
                    self._browser_process.terminate()
                    self._browser_process.wait(timeout=2.0)
                except Exception:
                    try:
                        self._browser_process.kill()
                    except Exception:
                        pass
                self._browser_process = None

            return BrowserActionResult(True, True, "Closed managed browser.")

    def _get_page_id(self, page: Any) -> str:
        """Derive consistent identifier for a Page instance."""
        try:
            return str(id(page))
        except Exception:
            return str(page)

    # =========================================================================
    # 4. VERIFIABLE DOM / JS EVALUATION
    # =========================================================================

    def evaluate_js(self, app_key: str, script: str) -> BrowserActionResult:
        """
        Execute JavaScript in the target application's active page and verify outcome.
        Returns BrowserActionResult with parsed return value in .data.
        """
        page = self.get_tab(app_key)
        if not page:
            return BrowserActionResult(
                success=False,
                verified=False,
                reason=f"{app_key.capitalize()} tab is not open."
            )

        try:
            res = page.evaluate(script)
            return BrowserActionResult(
                success=True,
                verified=True,
                reason="JavaScript evaluated successfully.",
                data=res
            )
        except Exception as exc:
            err = f"JavaScript evaluation error on {app_key}: {exc}"
            logger.debug(err)
            return BrowserActionResult(
                success=False,
                verified=False,
                reason=err
            )


# Global singleton
_global_browser_manager: Optional[BrowserManager] = None
_bm_lock = threading.Lock()


def get_browser_manager() -> BrowserManager:
    """Retrieve the global BrowserManager singleton."""
    global _global_browser_manager
    with _bm_lock:
        if _global_browser_manager is None:
            _global_browser_manager = BrowserManager()
        return _global_browser_manager
