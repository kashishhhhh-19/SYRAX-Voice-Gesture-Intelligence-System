"""
actions/whatsapp_actions.py - WhatsApp Web Voice Messaging with Strict Confirmation Gate
Implements contact lookup, message drafting, spoken read-back, and a strict confirmation
gate requiring explicit user approval before any message is transmitted.
Protects user privacy: message content is never stored in persistent log files.
"""

import threading
import time
import webbrowser
from typing import Optional, Tuple

import config
import pyautogui
from actions.focus_manager import get_focus_manager
from core.browser_manager import get_browser_manager
from core.conversation_state import ConversationState, get_conversation_state
from core.event_bus import Events, get_event_bus
from core.logger import get_logger

logger = get_logger("WhatsAppActions")


class WhatsAppStatus:
    """Status states for WhatsApp operations."""
    IDLE = "Idle"
    OPENING = "Opening WhatsApp Web"
    SEARCHING = "Searching Contact"
    DRAFTING = "Drafting Message"
    AWAITING_CONFIRMATION = "Awaiting Confirmation"
    SENT = "Sent"
    CANCELLED = "Cancelled"
    AUTH_REQUIRED = "Login / QR Code Required"


class WhatsAppActions:
    """
    Coordinates WhatsApp Web automations without storing credentials or passwords.
    Drafts messages in the active chat and enforces an unbreakable confirmation gate.
    Uses BrowserManager CDP as the primary verifiable layer, with FocusManager as fallback.
    """

    WHATSAPP_URL = "https://web.whatsapp.com"
    TITLE_KEYWORDS = ["whatsapp"]

    def __init__(self, focus_manager=None, browser_manager=None, conversation_state=None) -> None:
        self.focus_manager = focus_manager or get_focus_manager()
        self.browser_manager = browser_manager or get_browser_manager()
        self.conversation_state: ConversationState = conversation_state or get_conversation_state()
        self._event_bus = get_event_bus()
        self._current_status = WhatsAppStatus.IDLE
        self._lock = threading.RLock()

    def get_status(self) -> str:
        with self._lock:
            return self._current_status

    def open_whatsapp(self) -> Tuple[bool, str, str]:
        """
        Open WhatsApp Web in the browser.
        Primary: BrowserManager CDP with persistent profile.
        Fallback: OS standard browser.
        """
        # 1. Primary: BrowserManager CDP
        try:
            opened, page, reason = self.browser_manager.open_tab(self.WHATSAPP_URL, app_key="whatsapp")
            if opened:
                self._current_status = WhatsAppStatus.OPENING
                logger.info(f"Opened WhatsApp Web via BrowserManager CDP: {reason}")
                self._event_bus.emit(
                    Events.ACTIVITY_LOG,
                    category="BROWSER",
                    message="Launched WhatsApp Web tab via CDP."
                )

                # Check for QR code or login status
                time.sleep(1.0)
                res = self.browser_manager.evaluate_js(
                    "whatsapp",
                    "(() => { const qr = document.querySelector('canvas') || document.querySelector('div[data-ref]'); const chatList = document.querySelector('#pane-side'); return {qr_needed: !!qr && !chatList, ready: !!chatList}; })()"
                )
                if res.success and isinstance(res.data, dict) and res.data.get("qr_needed"):
                    prompt = self.prompt_login_or_qr_needed()
                    return True, "WhatsApp QR scan required.", prompt

                return True, "Opened WhatsApp Web", "WhatsApp Web is open."
        except Exception as cdp_err:
            logger.debug(f"WhatsApp CDP launch failed, falling back: {cdp_err}")

        # 2. Fallback: OS standard browser
        try:
            logger.info(f"Opening WhatsApp Web via OS fallback: {self.WHATSAPP_URL}")
            webbrowser.open_new_tab(self.WHATSAPP_URL)
            self._current_status = WhatsAppStatus.OPENING
            self._event_bus.emit(
                Events.ACTIVITY_LOG,
                category="BROWSER",
                message="Launched WhatsApp Web tab."
            )
            return True, "Opened WhatsApp Web", "WhatsApp Web is opening in your browser."
        except Exception as exc:
            logger.error(f"Failed to open WhatsApp Web: {exc}")
            return False, f"Error: {exc}", "Could not open WhatsApp Web in your browser."

    def ensure_whatsapp_focused(self) -> Tuple[bool, str]:
        """Bring WhatsApp Web browser tab into the foreground."""
        adapter = self.focus_manager._adapter
        hwnds = adapter.enum_windows()
        for hwnd in hwnds:
            if not adapter.is_window_visible(hwnd):
                continue
            title = adapter.get_window_text(hwnd)
            if not title:
                continue
            lower_title = title.lower()

            if any(ign in lower_title for ign in config.APP_WINDOW_TITLE_IGNORE):
                continue

            if any(kw in lower_title for kw in self.TITLE_KEYWORDS):
                if adapter.is_iconic(hwnd):
                    adapter.restore_window(hwnd)
                adapter.set_foreground_window(hwnd)
                adapter.sleep(0.08)
                if adapter.get_foreground_window() == hwnd:
                    return True, "WhatsApp Focused"

        return False, "Please open WhatsApp Web first."

    def prompt_login_or_qr_needed(self) -> str:
        """Inform user that WhatsApp Web requires QR code scan or manual login."""
        prompt = "Please scan the QR code to log in to WhatsApp Web in your browser."
        self._current_status = WhatsAppStatus.AUTH_REQUIRED
        self._event_bus.emit(
            Events.ASSISTANT_RESPONSE,
            text=prompt,
            source="whatsapp_actions"
        )
        self._event_bus.emit(
            Events.ACTIVITY_LOG,
            category="WARNING",
            message="WhatsApp Web login/QR code scan required."
        )
        return prompt

    def start_message_flow(
        self,
        contact: Optional[str] = None,
        message: Optional[str] = None
    ) -> Tuple[bool, str, str]:
        """
        Processes voice command to send a message.
        Handles slot filling if contact or message text is absent.
        Drafts message in compose box WITHOUT sending, and prompts for explicit confirmation.
        """
        # 1. Missing Contact Slot Filling
        if not contact or not contact.strip():
            self.conversation_state.set_pending_slot("contact_name", "send_message", {"message": message})
            spoken = "Who would you like to message on WhatsApp?"
            return True, "Prompting for contact", spoken

        # 2. Missing Message Slot Filling
        if not message or not message.strip():
            self.conversation_state.set_pending_slot("message_content", "send_message", {"contact": contact})
            spoken = f"What message would you like to send to {contact}?"
            return True, "Prompting for message content", spoken

        # 3. Both contact and message present: Begin drafting flow
        clean_contact = contact.strip()
        clean_msg = message.strip()

        # Update context
        self.conversation_state.last_contact = clean_contact
        self.conversation_state.touch()

        # Step 3a: Ensure browser is open with WhatsApp Web
        page = self.browser_manager.get_tab("whatsapp")
        if not page:
            self.open_whatsapp()
            time.sleep(1.0)
            page = self.browser_manager.get_tab("whatsapp")

        # Step 3b: Search for contact
        self._current_status = WhatsAppStatus.SEARCHING
        logger.info(f"Searching for contact: '{clean_contact}'")

        drafted_via_cdp = False
        if self.browser_manager.is_connected() and page:
            try:
                page.bring_to_front()
                # Focus search box
                self.browser_manager.evaluate_js(
                    "whatsapp",
                    """(() => {
                        const sb = document.querySelector('div[contenteditable=\"true\"][data-tab=\"3\"]') ||
                                   document.querySelector('div[aria-label=\"Search input text\"]') ||
                                   document.querySelector('div[contenteditable=\"true\"]');
                        if (sb) { sb.focus(); return true; }
                        return false;
                    })()"""
                )
                page.keyboard.type(clean_contact)
                time.sleep(0.4)

                # Check results for disambiguation
                eval_matches = self.browser_manager.evaluate_js(
                    "whatsapp",
                    """(() => {
                        const list = document.querySelectorAll('#pane-side span[title]');
                        const out = [];
                        list.forEach(el => {
                            const t = el.getAttribute('title');
                            if (t && !out.includes(t)) out.push(t);
                        });
                        return out.slice(0, 4);
                    })()"""
                )
                matches = eval_matches.data if (eval_matches.success and isinstance(eval_matches.data, list)) else []
                if len(matches) > 1 and not any(m.lower() == clean_contact.lower() for m in matches):
                    names_str = ", ".join(matches[:3])
                    self.conversation_state.set_pending_slot("disambiguate_contact", "send_message", {"matches": matches, "message": clean_msg})
                    return True, f"Multiple contacts: {names_str}", f"I found multiple contacts matching {clean_contact}: {names_str}. Which one should I message?"

                # Select contact
                page.keyboard.press("Enter")
                time.sleep(0.4)

                # Focus compose box and type draft message (DO NOT PRESS ENTER)
                self._current_status = WhatsAppStatus.DRAFTING
                self.browser_manager.evaluate_js(
                    "whatsapp",
                    """(() => {
                        const compose = document.querySelector('footer div[contenteditable=\"true\"]') ||
                                        document.querySelector('div[data-tab=\"10\"][contenteditable=\"true\"]');
                        if (compose) { compose.focus(); return true; }
                        return false;
                    })()"""
                )
                page.keyboard.type(clean_msg)
                drafted_via_cdp = True
            except Exception as cdp_flow_err:
                logger.debug(f"CDP drafting error, falling back to simulated shortcuts: {cdp_flow_err}")

        if not drafted_via_cdp:
            focused, msg = self.ensure_whatsapp_focused()
            if not focused:
                self.open_whatsapp()
                time.sleep(1.0)
                self.ensure_whatsapp_focused()

            try:
                pyautogui.hotkey("ctrl", "alt", "/")
                time.sleep(0.15)
                pyautogui.write(clean_contact, interval=0.04)
                time.sleep(0.3)
                pyautogui.press("enter")
                time.sleep(0.2)
                self._current_status = WhatsAppStatus.DRAFTING
                pyautogui.write(clean_msg, interval=0.02)
            except Exception as exc:
                logger.debug(f"Simulated message drafting: {exc}")

        # Step 3c: Register Pending Confirmation in ConversationState
        self.conversation_state.set_pending_confirmation(
            action_type="whatsapp_send",
            recipient=clean_contact,
            content=clean_msg
        )
        self._current_status = WhatsAppStatus.AWAITING_CONFIRMATION

        # Notify UI of pending confirmation card (Never stored in disk log)
        self._event_bus.emit(
            Events.WHATSAPP_CONFIRMATION_PENDING,
            recipient=clean_contact,
            content=clean_msg
        )
        self._event_bus.emit(
            Events.ACTIVITY_LOG,
            category="PRIVACY",
            message=f"Drafted WhatsApp message to {clean_contact}. Awaiting spoken confirmation."
        )

        readback_prompt = (
            f"I drafted a message to {clean_contact}: '{clean_msg}'. Should I send it?"
        )
        return True, f"Drafted message to {clean_contact}", readback_prompt

    def execute_confirmed_send(self) -> Tuple[bool, str, str]:
        """
        STRICT CONFIRMATION GATE:
        Called ONLY after the user speaks an explicit affirmation ('yes', 'send it', 'haan bhejo')
        or clicks the Send button on the GUI confirmation card.
        """
        pending = self.conversation_state.get_pending_confirmation()
        if not pending or pending.action_type != "whatsapp_send":
            return False, "No pending message", "There is no pending message to send."

        recipient = pending.recipient
        logger.info(f"CONFIRMATION GRANTED: Sending message to {recipient}")

        sent_via_cdp = False
        page = self.browser_manager.get_tab("whatsapp")
        if self.browser_manager.is_connected() and page:
            try:
                page.bring_to_front()
                page.keyboard.press("Enter")
                time.sleep(0.3)
                sent_via_cdp = True
            except Exception as cdp_send_err:
                logger.debug(f"CDP send failed: {cdp_send_err}")

        if not sent_via_cdp:
            self.ensure_whatsapp_focused()
            try:
                pyautogui.press("enter")
            except Exception as exc:
                logger.error(f"Error dispatching Enter key: {exc}")

        # Clear pending state
        self.conversation_state.clear_pending_confirmation()
        self._current_status = WhatsAppStatus.SENT

        self._event_bus.emit(
            Events.WHATSAPP_MESSAGE_SENT,
            recipient=recipient
        )
        self._event_bus.emit(
            Events.ACTIVITY_LOG,
            category="MESSAGING",
            message=f"WhatsApp message dispatched to {recipient}."
        )

        spoken = f"Message sent to {recipient}."
        return True, f"Sent message to {recipient}", spoken

    def cancel_pending_message(self) -> Tuple[bool, str, str]:
        """
        Cancels pending message. Clears text from compose box and discards confirmation state.
        """
        pending = self.conversation_state.get_pending_confirmation()
        recipient = pending.recipient if pending else "recipient"

        logger.info("CONFIRMATION REJECTED: Cancelling drafted WhatsApp message")

        cancelled_via_cdp = False
        page = self.browser_manager.get_tab("whatsapp")
        if self.browser_manager.is_connected() and page:
            try:
                page.bring_to_front()
                page.keyboard.down("Control")
                page.keyboard.press("a")
                page.keyboard.up("Control")
                page.keyboard.press("Backspace")
                cancelled_via_cdp = True
            except Exception as cdp_clear_err:
                logger.debug(f"CDP clear compose box error: {cdp_clear_err}")

        if not cancelled_via_cdp:
            self.ensure_whatsapp_focused()
            try:
                pyautogui.hotkey("ctrl", "a")
                pyautogui.press("backspace")
            except Exception as exc:
                logger.debug(f"Clearing compose box: {exc}")

        self.conversation_state.clear_pending_confirmation()
        self._current_status = WhatsAppStatus.CANCELLED

        self._event_bus.emit(
            Events.WHATSAPP_MESSAGE_CANCELLED,
            recipient=recipient
        )
        self._event_bus.emit(
            Events.ACTIVITY_LOG,
            category="MESSAGING",
            message="Pending message cancelled by user."
        )

        spoken = "Message cancelled."
        return True, "Cancelled message", spoken

    def close_whatsapp(self) -> Tuple[bool, str]:
        """Close SYRAX-opened WhatsApp Web tab via BrowserManager."""
        res = self.browser_manager.close_tab("whatsapp")
        if res.success:
            return True, res.reason

        def _close():
            pyautogui.hotkey("ctrl", "w")
            return True, "Closed WhatsApp window via shortcut"
        return self.ensure_whatsapp_focused() and _close()


# Global Singleton
_global_whatsapp_actions: Optional[WhatsAppActions] = None


def get_whatsapp_actions() -> WhatsAppActions:
    """Retrieve global WhatsAppActions singleton."""
    global _global_whatsapp_actions
    if _global_whatsapp_actions is None:
        _global_whatsapp_actions = WhatsAppActions()
    return _global_whatsapp_actions
