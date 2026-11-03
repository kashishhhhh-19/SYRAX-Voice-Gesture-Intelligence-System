"""
GestureFlow - Gesture Controller Test Suite
Tests PyAutoGUI dispatch isolation, mode switching, action mapping,
failsafe protection, and emergency-stop behavior without triggering real OS actions.
"""

import pytest
from app.config import ControlConfig
from app.gesture_controller import GestureController, ControlMode, ActionLogEntry
from app.gesture_recognition import GestureType, GestureResult


@pytest.fixture
def mock_controller():
    """Provides a GestureController with captured action invocations."""
    dispatched_actions = []

    def mock_executor(action_type: str, arg: str) -> bool:
        dispatched_actions.append((action_type, arg))
        return True

    controller = GestureController(
        config=ControlConfig(enabled_by_default=False, scroll_amount=180),
        action_executor=mock_executor
    )
    controller._test_dispatched = dispatched_actions
    return controller


class TestControllerSafety:
    """Verifies that actions are strictly gated by user permission."""

    def test_controls_disabled_by_default(self, mock_controller):
        """Application starts with controls disarmed."""
        assert mock_controller.is_enabled is False
        assert mock_controller.total_actions_executed == 0

    def test_actions_blocked_when_disarmed(self, mock_controller):
        """Triggered gestures produce NO action when disarmed."""
        swipe_res = GestureResult(
            gesture=GestureType.SWIPE_RIGHT,
            confidence=0.92,
            is_triggered=True,
            description="Swipe Right",
            cooldown_remaining=0.0
        )
        entry = mock_controller.process_gesture(swipe_res)
        assert entry is None
        assert len(mock_controller._test_dispatched) == 0
        assert mock_controller.total_actions_executed == 0

    def test_untriggered_gestures_produce_no_actions(self, mock_controller):
        """Even when armed, gestures where is_triggered is False produce no action."""
        mock_controller.enable_control()
        untriggered = GestureResult(
            gesture=GestureType.SWIPE_RIGHT,
            confidence=0.92,
            is_triggered=False,
            description="In motion",
            cooldown_remaining=0.4
        )
        entry = mock_controller.process_gesture(untriggered)
        assert entry is None
        assert len(mock_controller._test_dispatched) == 0

    def test_emergency_stop_halts_everything(self, mock_controller):
        """Emergency stop immediately halts control and records HALTED status."""
        mock_controller.enable_control()
        assert mock_controller.is_enabled is True

        mock_controller.emergency_stop()
        assert mock_controller.is_enabled is False
        assert "EMERGENCY" in mock_controller.last_action_desc

        # Further gestures must be blocked
        swipe_res = GestureResult(
            gesture=GestureType.SWIPE_RIGHT,
            confidence=0.95,
            is_triggered=True,
            description="Swipe Right",
            cooldown_remaining=0.0
        )
        assert mock_controller.process_gesture(swipe_res) is None
        assert len(mock_controller._test_dispatched) == 0


class TestPresentationMode:
    """Tests gesture mapping under Presentation Mode."""

    def test_presentation_navigation_actions(self, mock_controller):
        mock_controller.set_mode(ControlMode.PRESENTATION)
        mock_controller.enable_control()

        # 1. Swipe Right -> Next Slide
        swipe_r = GestureResult(GestureType.SWIPE_RIGHT, 0.92, True, "Swipe Right", 0.0)
        entry = mock_controller.process_gesture(swipe_r)
        assert entry is not None
        assert entry.status == "Executed"
        assert ("press", "right") in mock_controller._test_dispatched

        # 2. Swipe Left -> Previous Slide
        swipe_l = GestureResult(GestureType.SWIPE_LEFT, 0.92, True, "Swipe Left", 0.0)
        entry = mock_controller.process_gesture(swipe_l)
        assert entry is not None
        assert ("press", "left") in mock_controller._test_dispatched

        # 3. Pinch Out -> Zoom In (Ctrl + +)
        pinch = GestureResult(GestureType.PINCH_OUT, 0.88, True, "Pinch Out", 0.0)
        entry = mock_controller.process_gesture(pinch)
        assert entry is not None
        assert ("hotkey", "ctrl++") in mock_controller._test_dispatched

    def test_presentation_mode_ignores_scroll_gestures(self, mock_controller):
        """Scroll gestures should NOT execute actions in Presentation Mode."""
        mock_controller.set_mode(ControlMode.PRESENTATION)
        mock_controller.enable_control()

        point_up = GestureResult(GestureType.POINTING_UP, 0.94, True, "Point Up", 0.0)
        entry = mock_controller.process_gesture(point_up)
        assert entry is None
        assert len(mock_controller._test_dispatched) == 0

    def test_fist_activates_presentation_mode(self, mock_controller):
        """Fist arms controls when disarmed."""
        assert mock_controller.is_enabled is False
        fist = GestureResult(GestureType.FIST, 0.95, True, "Fist", 0.0)
        entry = mock_controller.process_gesture(fist)
        assert entry is not None
        assert entry.status == "Activated"
        assert mock_controller.is_enabled is True

    def test_fist_avoids_repeated_activation(self, mock_controller):
        """Fist does not repeatedly activate or spam when already armed."""
        mock_controller.enable_control()
        assert mock_controller.is_enabled is True

        fist = GestureResult(GestureType.FIST, 0.95, True, "Fist", 0.0)
        entry = mock_controller.process_gesture(fist)
        assert entry is None  # Quietly ignored when already active

    def test_open_palm_disables_controls(self, mock_controller):
        """Open palm immediately pauses/disables active controls."""
        mock_controller.enable_control()
        assert mock_controller.is_enabled is True

        palm = GestureResult(GestureType.OPEN_PALM, 0.96, True, "Open Palm", 0.0)
        entry = mock_controller.process_gesture(palm)
        assert entry is not None
        assert entry.status == "Paused"
        assert mock_controller.is_enabled is False


class TestScrollMode:
    """Tests gesture mapping under Scroll Mode."""

    def test_scroll_actions(self, mock_controller):
        mock_controller.set_mode(ControlMode.SCROLLING)
        mock_controller.enable_control()

        # Pointing Up -> Scroll Up
        up = GestureResult(GestureType.POINTING_UP, 0.94, True, "Point Up", 0.0)
        entry = mock_controller.process_gesture(up)
        assert entry is not None
        assert ("scroll", "180") in mock_controller._test_dispatched

        # Pointing Down -> Scroll Down
        down = GestureResult(GestureType.POINTING_DOWN, 0.94, True, "Point Down", 0.0)
        entry = mock_controller.process_gesture(down)
        assert entry is not None
        assert ("scroll", "-180") in mock_controller._test_dispatched

    def test_scroll_mode_ignores_swipe_gestures(self, mock_controller):
        """Presentation gestures should NOT execute actions in Scroll Mode."""
        mock_controller.set_mode(ControlMode.SCROLLING)
        mock_controller.enable_control()

        swipe_r = GestureResult(GestureType.SWIPE_RIGHT, 0.92, True, "Swipe Right", 0.0)
        entry = mock_controller.process_gesture(swipe_r)
        assert entry is None
        assert len(mock_controller._test_dispatched) == 0


class TestUnifiedMode:
    """Tests Unified Mode supporting both presentation and scrolling gestures."""

    def test_unified_mode_handles_all_gestures(self, mock_controller):
        mock_controller.set_mode(ControlMode.UNIFIED)
        mock_controller.enable_control()

        # Swipe
        mock_controller.process_gesture(GestureResult(GestureType.SWIPE_RIGHT, 0.92, True, "Swipe Right", 0.0))
        assert ("press", "right") in mock_controller._test_dispatched

        # Scroll
        mock_controller.process_gesture(GestureResult(GestureType.POINTING_UP, 0.94, True, "Point Up", 0.0))
        assert ("scroll", "180") in mock_controller._test_dispatched

        # Zoom
        mock_controller.process_gesture(GestureResult(GestureType.PINCH_OUT, 0.88, True, "Pinch Out", 0.0))
        assert ("hotkey", "ctrl++") in mock_controller._test_dispatched
