"""
tests/test_whatsapp_actions.py - Unit tests for WhatsAppActions
Validates slot-filling, drafting, spoken readback, and the unbreakable confirmation gate.
"""

import unittest
from unittest.mock import MagicMock, patch
from actions.whatsapp_actions import WhatsAppActions, WhatsAppStatus
from core.conversation_state import ConversationState


class TestWhatsAppActions(unittest.TestCase):
    def setUp(self):
        self.mock_focus = MagicMock()
        self.mock_adapter = MagicMock()
        self.mock_focus._adapter = self.mock_adapter
        self.mock_bm = MagicMock()
        self.mock_bm.is_connected.return_value = False
        self.mock_bm.get_tab.return_value = None
        self.mock_bm.open_tab.return_value = (False, None, "CDP disabled in mock test")
        self.conv_state = ConversationState()
        self.wa = WhatsAppActions(
            focus_manager=self.mock_focus,
            browser_manager=self.mock_bm,
            conversation_state=self.conv_state
        )

    def test_missing_contact_triggers_slot_filling(self):
        success, desc, spoken = self.wa.start_message_flow(contact=None, message="hello")
        self.assertTrue(success)
        self.assertIn("Who would you like to message", spoken)
        slot_info = self.conv_state.get_pending_slot()
        self.assertIsNotNone(slot_info)
        self.assertEqual(slot_info[0], "contact_name")

    def test_missing_message_triggers_slot_filling(self):
        success, desc, spoken = self.wa.start_message_flow(contact="Rahul", message=None)
        self.assertTrue(success)
        self.assertIn("What message would you like to send to Rahul", spoken)
        slot_info = self.conv_state.get_pending_slot()
        self.assertIsNotNone(slot_info)
        self.assertEqual(slot_info[0], "message_content")

    @patch("actions.whatsapp_actions.WhatsAppActions.ensure_whatsapp_focused", return_value=(True, "Focused"))
    @patch("pyautogui.write")
    @patch("pyautogui.press")
    def test_full_command_drafts_and_prompts_confirmation(self, mock_press, mock_write, mock_focus):
        success, desc, spoken = self.wa.start_message_flow(contact="Rahul", message="how are you")
        self.assertTrue(success)
        self.assertIn("drafted a message to Rahul", spoken)
        self.assertIn("how are you", spoken)
        self.assertIn("Should I send it?", spoken)

        # Verify confirmation state was set
        pending = self.conv_state.get_pending_confirmation()
        self.assertIsNotNone(pending)
        self.assertEqual(pending.recipient, "Rahul")
        self.assertEqual(pending.content, "how are you")

        # Verify Enter was NOT pressed during drafting
        # mock_press should have been called for "enter" only during contact selection, not after drafting
        self.assertEqual(self.wa.get_status(), WhatsAppStatus.AWAITING_CONFIRMATION)

    @patch("actions.whatsapp_actions.WhatsAppActions.ensure_whatsapp_focused", return_value=(True, "Focused"))
    @patch("pyautogui.press")
    def test_confirmation_granted_sends_message(self, mock_press, mock_focus):
        self.conv_state.set_pending_confirmation("whatsapp_send", "Rahul", "how are you")
        success, msg, spoken = self.wa.execute_confirmed_send()

        self.assertTrue(success)
        self.assertIn("Message sent to Rahul", spoken)
        mock_press.assert_called_with("enter")
        self.assertIsNone(self.conv_state.get_pending_confirmation())
        self.assertEqual(self.wa.get_status(), WhatsAppStatus.SENT)

    @patch("actions.whatsapp_actions.WhatsAppActions.ensure_whatsapp_focused", return_value=(True, "Focused"))
    @patch("pyautogui.hotkey")
    @patch("pyautogui.press")
    def test_cancellation_clears_draft_and_state(self, mock_press, mock_hotkey, mock_focus):
        self.conv_state.set_pending_confirmation("whatsapp_send", "Rahul", "how are you")
        success, msg, spoken = self.wa.cancel_pending_message()

        self.assertTrue(success)
        self.assertEqual(spoken, "Message cancelled.")
        mock_hotkey.assert_called_with("ctrl", "a")
        mock_press.assert_called_with("backspace")
        self.assertIsNone(self.conv_state.get_pending_confirmation())
        self.assertEqual(self.wa.get_status(), WhatsAppStatus.CANCELLED)

    def test_refuse_send_when_no_pending_confirmation(self):
        success, msg, spoken = self.wa.execute_confirmed_send()
        self.assertFalse(success)
        self.assertIn("no pending message", spoken)

    def test_close_whatsapp(self):
        from core.browser_manager import BrowserActionResult
        self.mock_bm.close_tab.return_value = BrowserActionResult(
            success=True,
            verified=True,
            reason="Closed whatsapp tab."
        )
        success, msg = self.wa.close_whatsapp()
        self.assertTrue(success)
        self.mock_bm.close_tab.assert_called_with("whatsapp")


if __name__ == "__main__":
    unittest.main()
