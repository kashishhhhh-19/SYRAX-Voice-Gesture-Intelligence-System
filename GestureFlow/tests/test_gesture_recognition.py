"""
GestureFlow - Comprehensive Unit Test Suite
Tests gesture classification, motion velocity thresholds, debounce logic,
cooldown timers, missing landmarks, and controller safety mechanisms.
Does NOT require a physical webcam.
"""

import math
import time
import pytest
from typing import List

from app.config import GestureThresholds, CooldownConfig, ControlConfig
from app.hand_tracking import (
    HandData, LandmarkPoint,
    WRIST, THUMB_CMC, THUMB_MCP, THUMB_IP, THUMB_TIP,
    INDEX_FINGER_MCP, INDEX_FINGER_PIP, INDEX_FINGER_DIP, INDEX_FINGER_TIP,
    MIDDLE_FINGER_MCP, MIDDLE_FINGER_PIP, MIDDLE_FINGER_DIP, MIDDLE_FINGER_TIP,
    RING_FINGER_MCP, RING_FINGER_PIP, RING_FINGER_DIP, RING_FINGER_TIP,
    PINKY_MCP, PINKY_PIP, PINKY_DIP, PINKY_TIP
)
from app.gesture_recognition import GestureRecognizer, GestureType, GestureResult
from app.gesture_controller import GestureController, ControlMode


# -------------------------------------------------------------------------
# Synthetic Landmark Fixture Generators
# -------------------------------------------------------------------------

def create_synthetic_hand(
    wrist_xy=(0.5, 0.7),
    index_state="curled",    # "curled" or "extended_up" or "extended_down" or "extended_right"
    middle_state="curled",   # "curled" or "extended"
    ring_state="curled",     # "curled" or "extended"
    pinky_state="curled",    # "curled" or "extended"
    thumb_state="curled",    # "curled" or "extended"
    pinch_dist_norm=0.04,    # Distance between thumb tip and index tip
    hand_scale=0.20
) -> HandData:
    """Generates a complete 21-point MediaPipe hand landmark hierarchy."""
    wx, wy = wrist_xy
    landmarks: List[LandmarkPoint] = [None] * 21

    # Landmark 0: Wrist
    landmarks[WRIST] = LandmarkPoint(0, wx, wy, 0.0, int(wx * 640), int(wy * 480))

    # Knuckle base (MCP) positions
    mcp_y = wy - hand_scale
    mcp_xs = {
        INDEX_FINGER_MCP: wx - 0.05,
        MIDDLE_FINGER_MCP: wx,
        RING_FINGER_MCP: wx + 0.04,
        PINKY_MCP: wx + 0.08
    }

    # Helper to lay out a 4-point finger (MCP, PIP, DIP, TIP)
    def layout_finger(mcp_idx, pip_idx, dip_idx, tip_idx, state):
        base_x = mcp_xs[mcp_idx]
        base_y = mcp_y
        landmarks[mcp_idx] = LandmarkPoint(mcp_idx, base_x, base_y, 0.0, int(base_x * 640), int(base_y * 480))

        if state == "curled":
            # Folded down towards palm center
            pip_y = base_y - 0.03
            dip_y = base_y + 0.02
            tip_y = base_y + 0.04
            landmarks[pip_idx] = LandmarkPoint(pip_idx, base_x, pip_y, 0.0, int(base_x * 640), int(pip_y * 480))
            landmarks[dip_idx] = LandmarkPoint(dip_idx, base_x, dip_y, 0.0, int(base_x * 640), int(dip_y * 480))
            landmarks[tip_idx] = LandmarkPoint(tip_idx, base_x, tip_y, 0.0, int(base_x * 640), int(tip_y * 480))
        elif state == "extended_up" or state == "extended":
            # Extended straight upward
            pip_y = base_y - 0.06
            dip_y = base_y - 0.12
            tip_y = base_y - 0.18
            landmarks[pip_idx] = LandmarkPoint(pip_idx, base_x, pip_y, 0.0, int(base_x * 640), int(pip_y * 480))
            landmarks[dip_idx] = LandmarkPoint(dip_idx, base_x, dip_y, 0.0, int(base_x * 640), int(dip_y * 480))
            landmarks[tip_idx] = LandmarkPoint(tip_idx, base_x, tip_y, 0.0, int(base_x * 640), int(tip_y * 480))
        elif state == "extended_down":
            # Extended straight downward
            pip_y = base_y + 0.06
            dip_y = base_y + 0.12
            tip_y = base_y + 0.18
            landmarks[pip_idx] = LandmarkPoint(pip_idx, base_x, pip_y, 0.0, int(base_x * 640), int(pip_y * 480))
            landmarks[dip_idx] = LandmarkPoint(dip_idx, base_x, dip_y, 0.0, int(base_x * 640), int(dip_y * 480))
            landmarks[tip_idx] = LandmarkPoint(tip_idx, base_x, tip_y, 0.0, int(base_x * 640), int(tip_y * 480))
        elif state == "extended_horizontal":
            # Extended to the right horizontally
            landmarks[pip_idx] = LandmarkPoint(pip_idx, base_x + 0.06, base_y, 0.0, int((base_x + 0.06) * 640), int(base_y * 480))
            landmarks[dip_idx] = LandmarkPoint(dip_idx, base_x + 0.12, base_y, 0.0, int((base_x + 0.12) * 640), int(base_y * 480))
            landmarks[tip_idx] = LandmarkPoint(tip_idx, base_x + 0.18, base_y, 0.0, int((base_x + 0.18) * 640), int(base_y * 480))

    # Layout fingers
    layout_finger(INDEX_FINGER_MCP, INDEX_FINGER_PIP, INDEX_FINGER_DIP, INDEX_FINGER_TIP, index_state)
    layout_finger(MIDDLE_FINGER_MCP, MIDDLE_FINGER_PIP, MIDDLE_FINGER_DIP, MIDDLE_FINGER_TIP, middle_state)
    layout_finger(RING_FINGER_MCP, RING_FINGER_PIP, RING_FINGER_DIP, RING_FINGER_TIP, ring_state)
    layout_finger(PINKY_MCP, PINKY_PIP, PINKY_DIP, PINKY_TIP, pinky_state)

    # Layout Thumb
    t_base_x = wx - 0.06
    landmarks[THUMB_CMC] = LandmarkPoint(THUMB_CMC, t_base_x, wy - 0.05, 0.0, int(t_base_x * 640), int((wy - 0.05) * 480))
    landmarks[THUMB_MCP] = LandmarkPoint(THUMB_MCP, t_base_x - 0.03, wy - 0.09, 0.0, int((t_base_x - 0.03) * 640), int((wy - 0.09) * 480))
    landmarks[THUMB_IP] = LandmarkPoint(THUMB_IP, t_base_x - 0.05, wy - 0.13, 0.0, int((t_base_x - 0.05) * 640), int((wy - 0.13) * 480))

    if thumb_state == "extended":
        landmarks[THUMB_TIP] = LandmarkPoint(THUMB_TIP, t_base_x - 0.09, wy - 0.17, 0.0, int((t_base_x - 0.09) * 640), int((wy - 0.17) * 480))
    elif thumb_state == "pinch":
        # Thumb tip positioned pinch_dist_norm away from index tip
        idx_tip = landmarks[INDEX_FINGER_TIP]
        landmarks[THUMB_TIP] = LandmarkPoint(
            THUMB_TIP, idx_tip.x - pinch_dist_norm, idx_tip.y, 0.0,
            int((idx_tip.x - pinch_dist_norm) * 640), int(idx_tip.y * 480)
        )
    else: # curled across palm
        landmarks[THUMB_TIP] = LandmarkPoint(THUMB_TIP, wx - 0.02, wy - 0.10, 0.0, int((wx - 0.02) * 640), int((wy - 0.10) * 480))

    return HandData(
        landmarks=landmarks,
        handedness="Right",
        confidence=0.95,
        bbox_pixel=(100, 100, 300, 300),
        bbox_norm=(0.2, 0.2, 0.8, 0.8),
        palm_center_norm=(wx, wy - hand_scale * 0.5),
        palm_center_pixel=(int(wx * 640), int((wy - hand_scale * 0.5) * 480)),
        hand_scale=hand_scale
    )


# -------------------------------------------------------------------------
# Test Cases
# -------------------------------------------------------------------------

class TestGestureClassification:
    """Verifies static hand posture classification."""

    def test_fist_recognition(self):
        """All fingers curled -> Fist detected."""
        hand = create_synthetic_hand(
            index_state="curled",
            middle_state="curled",
            ring_state="curled",
            pinky_state="curled",
            thumb_state="curled"
        )
        recognizer = GestureRecognizer()

        # Feed 3 stable frames to satisfy consecutive frame requirement
        result = None
        for i in range(3):
            result = recognizer.recognize([hand], current_time=100.0 + i * 0.033)

        assert result is not None
        assert result.gesture == GestureType.FIST
        assert result.confidence >= 0.85
        assert result.is_triggered is True

    def test_open_palm_recognition(self):
        """All 5 fingers extended -> Open Palm detected."""
        hand = create_synthetic_hand(
            index_state="extended",
            middle_state="extended",
            ring_state="extended",
            pinky_state="extended",
            thumb_state="extended"
        )
        recognizer = GestureRecognizer()

        result = None
        for i in range(3):
            result = recognizer.recognize([hand], current_time=100.0 + i * 0.033)

        assert result is not None
        assert result.gesture == GestureType.OPEN_PALM
        assert result.confidence >= 0.85

    def test_pointing_up_recognition(self):
        """Only index finger extended vertically up -> Pointing Up detected."""
        hand = create_synthetic_hand(
            index_state="extended_up",
            middle_state="curled",
            ring_state="curled",
            pinky_state="curled",
            thumb_state="curled"
        )
        recognizer = GestureRecognizer()

        result = None
        for i in range(3):
            result = recognizer.recognize([hand], current_time=100.0 + i * 0.033)

        assert result is not None
        assert result.gesture == GestureType.POINTING_UP
        assert result.confidence >= 0.85

    def test_pointing_down_recognition(self):
        """Only index finger extended vertically down -> Pointing Down detected."""
        hand = create_synthetic_hand(
            index_state="extended_down",
            middle_state="curled",
            ring_state="curled",
            pinky_state="curled",
            thumb_state="curled"
        )
        recognizer = GestureRecognizer()

        result = None
        for i in range(3):
            result = recognizer.recognize([hand], current_time=100.0 + i * 0.033)

        assert result is not None
        assert result.gesture == GestureType.POINTING_DOWN
        assert result.confidence >= 0.85

    def test_pointing_horizontal_not_pointing_up_or_down(self):
        """Index extended horizontally (out of vertical tolerance) -> Not classified as Pointing Up/Down."""
        hand = create_synthetic_hand(
            index_state="extended_horizontal",
            middle_state="curled",
            ring_state="curled",
            pinky_state="curled",
            thumb_state="curled"
        )
        recognizer = GestureRecognizer()

        result = None
        for i in range(3):
            result = recognizer.recognize([hand], current_time=100.0 + i * 0.033)

        assert result is not None
        assert result.gesture not in (GestureType.POINTING_UP, GestureType.POINTING_DOWN)


class TestMotionGestures:
    """Tests dynamic swipe and pinch gestures with motion history buffers."""

    def test_swipe_right_motion_detection(self):
        """Simulates rapid rightward movement across frames -> Swipe Right triggered."""
        recognizer = GestureRecognizer()
        t = 100.0

        # Feed 6 frames moving rapidly to the right (dx = +0.25 in 0.20 sec => vx = 1.25 units/sec)
        results = []
        for i in range(6):
            x = 0.30 + (i * 0.05)  # Moves from 0.30 to 0.55
            hand = create_synthetic_hand(
                wrist_xy=(x, 0.5),
                index_state="extended",
                middle_state="extended",
                ring_state="extended",
                pinky_state="extended",
                thumb_state="extended"
            )
            res = recognizer.recognize([hand], current_time=t + (i * 0.033))
            results.append(res)

        assert any(r.gesture == GestureType.SWIPE_RIGHT and r.is_triggered for r in results)

    def test_swipe_left_motion_detection(self):
        """Simulates rapid leftward movement across frames -> Swipe Left triggered."""
        recognizer = GestureRecognizer()
        t = 100.0

        # Feed 6 frames moving rapidly to the left (dx = -0.25 in 0.20 sec => vx = -1.25 units/sec)
        results = []
        for i in range(6):
            x = 0.70 - (i * 0.05)  # Moves from 0.70 to 0.45
            hand = create_synthetic_hand(
                wrist_xy=(x, 0.5),
                index_state="extended",
                middle_state="extended",
                ring_state="extended",
                pinky_state="extended",
                thumb_state="extended"
            )
            res = recognizer.recognize([hand], current_time=t + (i * 0.033))
            results.append(res)

        assert any(r.gesture == GestureType.SWIPE_LEFT and r.is_triggered for r in results)

    def test_stationary_hand_does_not_trigger_swipe(self):
        """Stationary hand with minor coordinate jitter does NOT trigger swipe."""
        recognizer = GestureRecognizer()
        t = 100.0

        # Minor stationary jitter +/- 0.002
        results = []
        for i in range(12):
            jitter = 0.002 if (i % 2 == 0) else -0.002
            hand = create_synthetic_hand(
                wrist_xy=(0.5 + jitter, 0.5),
                index_state="extended",
                middle_state="extended",
                ring_state="extended",
                pinky_state="extended",
                thumb_state="extended"
            )
            res = recognizer.recognize([hand], current_time=t + (i * 0.033))
            results.append(res)

        for res in results:
            assert res.gesture not in (GestureType.SWIPE_RIGHT, GestureType.SWIPE_LEFT)

    def test_pinch_out_expansion_detection(self):
        """Simulates fingers expanding outward from a pinch -> Pinch Out triggered."""
        recognizer = GestureRecognizer()
        t = 100.0

        result = None
        for i in range(6):
            # Pinch distance expands from 0.02 to 0.12
            pinch_dist = 0.02 + (i * 0.02)
            hand = create_synthetic_hand(
                wrist_xy=(0.5, 0.5),
                index_state="extended_up",
                thumb_state="pinch",
                pinch_dist_norm=pinch_dist,
                hand_scale=0.20
            )
            result = recognizer.recognize([hand], current_time=t + (i * 0.033))

        assert result is not None
        assert result.gesture == GestureType.PINCH_OUT


class TestCooldownAndDebouncing:
    """Verifies that cooldowns and frame stabilization prevent duplicate accidental triggers."""

    def test_isolated_single_frame_noise_filtered_out(self):
        """A single frame of a gesture does NOT trigger an action (requires stability)."""
        recognizer = GestureRecognizer()
        fist_hand = create_synthetic_hand(index_state="curled", middle_state="curled", ring_state="curled", pinky_state="curled")

        # 1 frame only
        result = recognizer.recognize([fist_hand], current_time=10.0)
        assert result.is_triggered is False

    def test_cooldown_prevents_immediate_repeated_trigger(self):
        """A triggered gesture cannot re-trigger during its cooldown window."""
        recognizer = GestureRecognizer()
        fist_hand = create_synthetic_hand(index_state="curled", middle_state="curled", ring_state="curled", pinky_state="curled")

        # Confirm 3 frames to trigger
        t = 10.0
        r1 = recognizer.recognize([fist_hand], current_time=t + 0.00)
        r2 = recognizer.recognize([fist_hand], current_time=t + 0.03)
        r3 = recognizer.recognize([fist_hand], current_time=t + 0.06)
        assert r3.is_triggered is True

        # Next frame immediately within cooldown period (0.10s later, cooldown is 1.0s)
        r4 = recognizer.recognize([fist_hand], current_time=t + 0.16)
        assert r4.is_triggered is False
        assert r4.cooldown_remaining > 0.0


class TestInvalidAndMissingInputs:
    """Ensures robustness against empty lists, None, or corrupt landmark arrays."""

    def test_empty_hands_list(self):
        recognizer = GestureRecognizer()
        res = recognizer.recognize([])
        assert res.gesture == GestureType.NONE
        assert res.is_triggered is False

    def test_none_hands_input(self):
        recognizer = GestureRecognizer()
        res = recognizer.recognize(None)
        assert res.gesture == GestureType.NONE
        assert res.is_triggered is False

    def test_hand_with_truncated_landmarks(self):
        recognizer = GestureRecognizer()
        incomplete_hand = HandData(
            landmarks=[LandmarkPoint(0, 0.5, 0.5, 0.0, 320, 240)], # Only 1 landmark instead of 21
            handedness="Right",
            confidence=0.5,
            bbox_pixel=(0, 0, 10, 10),
            bbox_norm=(0, 0, 1, 1),
            palm_center_norm=(0.5, 0.5),
            palm_center_pixel=(320, 240),
            hand_scale=0.1
        )
        res = recognizer.recognize([incomplete_hand])
        assert res.gesture == GestureType.NONE
        assert res.is_triggered is False


class TestGestureControllerSafety:
    """Verifies that PyAutoGUI commands are strictly protected and disabled by default."""

    def test_actions_blocked_when_controls_disabled(self):
        """No actions are executed when controller is disabled."""
        controller = GestureController()
        assert controller.is_enabled is False

        # Simulate triggered swipe right
        swipe_result = GestureResult(
            gesture=GestureType.SWIPE_RIGHT,
            confidence=0.95,
            is_triggered=True,
            description="Swipe Right",
            cooldown_remaining=0.0
        )
        log_entry = controller.process_gesture(swipe_result)
        assert log_entry is None
        assert controller.total_actions_executed == 0

    def test_actions_executed_when_controls_enabled(self):
        """Actions execute when controller is enabled."""
        actions_received = []
        def mock_exec(action_type, arg):
            actions_received.append((action_type, arg))
            return True

        controller = GestureController(action_executor=mock_exec)
        controller.enable_control()
        assert controller.is_enabled is True

        swipe_result = GestureResult(
            gesture=GestureType.SWIPE_RIGHT,
            confidence=0.95,
            is_triggered=True,
            description="Swipe Right",
            cooldown_remaining=0.0
        )
        log_entry = controller.process_gesture(swipe_result)
        assert log_entry is not None
        assert log_entry.status == "Executed"
        assert controller.total_actions_executed == 1
        assert len(actions_received) == 1
        assert actions_received[0] == ("press", "right")

    def test_open_palm_disables_controls_safely(self):
        """Open palm immediately pauses/disables computer control."""
        controller = GestureController()
        controller.enable_control()
        assert controller.is_enabled is True

        palm_result = GestureResult(
            gesture=GestureType.OPEN_PALM,
            confidence=0.96,
            is_triggered=True,
            description="Open Palm",
            cooldown_remaining=0.0
        )
        log_entry = controller.process_gesture(palm_result)
        assert log_entry is not None
        assert log_entry.status == "Paused"
        assert controller.is_enabled is False

    def test_emergency_stop_halts_all_controls(self):
        """Emergency stop immediately halts control."""
        controller = GestureController()
        controller.enable_control()
        controller.emergency_stop()
        assert controller.is_enabled is False
        assert "EMERGENCY" in controller.last_action_desc
