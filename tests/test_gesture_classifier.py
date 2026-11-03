"""
tests/test_gesture_classifier.py - Unit Tests for GestureClassifier
Tests pure landmark classification functions and temporal tracking:
- Fist detection & hold-to-toggle (~1.0s)
- Steady open palm play/pause (~0.5s) vs fast swipe differentiation
- Swipe right (next video) & swipe left (previous video)
- Two-finger forward (right) & rewind (left)
- One-finger scroll up & down
- Pinch zoom in (pinch out) & zoom out (pinch in)
- Cooldown and debounce timing
"""

import unittest
from typing import List, Tuple

import config
from gesture.gesture_classifier import (
    GestureClassifier,
    classify_pose,
    get_pinch_distance,
    is_fist,
    is_one_finger,
    is_open_palm,
    is_two_fingers,
    WRIST,
    THUMB_TIP,
    INDEX_TIP,
    MIDDLE_TIP,
    RING_TIP,
    PINKY_TIP,
)


def make_landmarks(
    wrist: Tuple[float, float] = (0.5, 0.7),
    thumb_tip: Tuple[float, float] = (0.45, 0.65),
    index_tip: Tuple[float, float] = (0.5, 0.6),
    middle_tip: Tuple[float, float] = (0.55, 0.6),
    ring_tip: Tuple[float, float] = (0.6, 0.6),
    pinky_tip: Tuple[float, float] = (0.65, 0.6),
    index_pip: Tuple[float, float] = (0.5, 0.65),
    middle_pip: Tuple[float, float] = (0.55, 0.65),
    ring_pip: Tuple[float, float] = (0.6, 0.65),
    pinky_pip: Tuple[float, float] = (0.65, 0.65),
) -> List[Tuple[float, float]]:
    """Helper to synthesize 21 normalized landmarks."""
    lm = [(wrist[0], wrist[1]) for _ in range(21)]
    lm[WRIST] = wrist
    lm[THUMB_TIP] = thumb_tip
    lm[INDEX_TIP] = index_tip
    lm[MIDDLE_TIP] = middle_tip
    lm[RING_TIP] = ring_tip
    lm[PINKY_TIP] = pinky_tip

    lm[6] = index_pip
    lm[10] = middle_pip
    lm[14] = ring_pip
    lm[18] = pinky_pip
    return lm


def make_fist_landmarks(x_center: float = 0.5, y_center: float = 0.6) -> List[Tuple[float, float]]:
    """Generate landmarks for a tightly closed fist."""
    wrist = (x_center, y_center + 0.15)
    return make_landmarks(
        wrist=wrist,
        thumb_tip=(x_center - 0.02, y_center + 0.05),
        index_tip=(x_center - 0.03, y_center + 0.04),
        middle_tip=(x_center, y_center + 0.04),
        ring_tip=(x_center + 0.03, y_center + 0.04),
        pinky_tip=(x_center + 0.05, y_center + 0.05),
        index_pip=(x_center - 0.03, y_center + 0.03),
        middle_pip=(x_center, y_center + 0.03),
        ring_pip=(x_center + 0.03, y_center + 0.03),
        pinky_pip=(x_center + 0.05, y_center + 0.03),
    )


def make_open_palm_landmarks(x_center: float = 0.5, y_center: float = 0.5) -> List[Tuple[float, float]]:
    """Generate landmarks for an open hand with all 5 fingers fully extended."""
    wrist = (x_center, y_center + 0.25)
    return make_landmarks(
        wrist=wrist,
        thumb_tip=(x_center - 0.18, y_center),
        index_tip=(x_center - 0.08, y_center - 0.25),
        middle_tip=(x_center, y_center - 0.28),
        ring_tip=(x_center + 0.08, y_center - 0.25),
        pinky_tip=(x_center + 0.16, y_center - 0.18),
        index_pip=(x_center - 0.08, y_center - 0.10),
        middle_pip=(x_center, y_center - 0.10),
        ring_pip=(x_center + 0.08, y_center - 0.10),
        pinky_pip=(x_center + 0.16, y_center - 0.08),
    )


def make_two_fingers_landmarks(x_center: float = 0.5, y_center: float = 0.5) -> List[Tuple[float, float]]:
    """Generate landmarks for index + middle extended, ring + pinky curled."""
    wrist = (x_center, y_center + 0.25)
    return make_landmarks(
        wrist=wrist,
        thumb_tip=(x_center - 0.04, y_center + 0.10),
        index_tip=(x_center - 0.04, y_center - 0.22), # Extended
        middle_tip=(x_center + 0.04, y_center - 0.22),# Extended
        ring_tip=(x_center + 0.06, y_center + 0.08),  # Curled
        pinky_tip=(x_center + 0.09, y_center + 0.09), # Curled
        index_pip=(x_center - 0.04, y_center - 0.08),
        middle_pip=(x_center + 0.04, y_center - 0.08),
        ring_pip=(x_center + 0.06, y_center + 0.04),
        pinky_pip=(x_center + 0.09, y_center + 0.05),
    )


def make_one_finger_landmarks(x_center: float = 0.5, y_center: float = 0.5) -> List[Tuple[float, float]]:
    """Generate landmarks for index extended only."""
    wrist = (x_center, y_center + 0.25)
    return make_landmarks(
        wrist=wrist,
        thumb_tip=(x_center - 0.04, y_center + 0.10),
        index_tip=(x_center, y_center - 0.24),         # Extended
        middle_tip=(x_center + 0.04, y_center + 0.08), # Curled
        ring_tip=(x_center + 0.06, y_center + 0.08),  # Curled
        pinky_tip=(x_center + 0.09, y_center + 0.09), # Curled
        index_pip=(x_center, y_center - 0.08),
        middle_pip=(x_center + 0.04, y_center + 0.04),
        ring_pip=(x_center + 0.06, y_center + 0.04),
        pinky_pip=(x_center + 0.09, y_center + 0.05),
    )


def make_pinch_landmarks(thumb_tip: Tuple[float, float], index_tip: Tuple[float, float]) -> List[Tuple[float, float]]:
    """Generate landmarks for a pinch pose where remaining fingers are curled."""
    return make_landmarks(
        wrist=(0.5, 0.75),
        thumb_tip=thumb_tip,
        index_tip=index_tip,
        middle_tip=(0.55, 0.70), # Curled
        ring_tip=(0.60, 0.70),   # Curled
        pinky_tip=(0.65, 0.70),  # Curled
        index_pip=(0.50, 0.55),
        middle_pip=(0.55, 0.65),
        ring_pip=(0.60, 0.65),
        pinky_pip=(0.65, 0.65),
    )


class TestGestureClassifier(unittest.TestCase):
    """Test suite for pure landmark classification and temporal tracking."""

    def setUp(self) -> None:
        self.classifier = GestureClassifier()

    def test_pure_fist_classification(self) -> None:
        """Verify is_fist identifies closed fist landmarks."""
        fist = make_fist_landmarks()
        ok, conf = is_fist(fist)
        self.assertTrue(ok)
        self.assertGreaterEqual(conf, 0.85)

        palm = make_open_palm_landmarks()
        ok_palm, _ = is_fist(palm)
        self.assertFalse(ok_palm)

    def test_pure_open_palm_classification(self) -> None:
        """Verify is_open_palm identifies open hand landmarks."""
        palm = make_open_palm_landmarks()
        ok, conf = is_open_palm(palm)
        self.assertTrue(ok)
        self.assertGreaterEqual(conf, 0.85)

        fist = make_fist_landmarks()
        ok_fist, _ = is_open_palm(fist)
        self.assertFalse(ok_fist)

    def test_pure_two_fingers_classification(self) -> None:
        """Verify is_two_fingers identifies index + middle fingers extended."""
        two = make_two_fingers_landmarks()
        ok, conf = is_two_fingers(two)
        self.assertTrue(ok)
        self.assertGreaterEqual(conf, 0.90)

        one = make_one_finger_landmarks()
        ok_one, _ = is_two_fingers(one)
        self.assertFalse(ok_one)

    def test_pure_one_finger_classification(self) -> None:
        """Verify is_one_finger identifies index finger pointing."""
        one = make_one_finger_landmarks()
        ok, conf = is_one_finger(one)
        self.assertTrue(ok)
        self.assertGreaterEqual(conf, 0.85)

        two = make_two_fingers_landmarks()
        ok_two, _ = is_one_finger(two)
        self.assertFalse(ok_two)

    def test_pinch_distance_calculation(self) -> None:
        """Verify get_pinch_distance returns Euclidean distance between thumb and index tips."""
        lm = make_landmarks(thumb_tip=(0.5, 0.5), index_tip=(0.53, 0.54))
        # hypot(0.03, 0.04) = 0.05
        dist = get_pinch_distance(lm)
        self.assertAlmostEqual(dist, 0.05, places=3)

    def test_fist_hold_toggles_mode(self) -> None:
        """Verify holding a Fist for ~1.0s triggers FIST_TOGGLE."""
        fist = make_fist_landmarks()

        # Frame 1: t=0.0
        res1 = self.classifier.process_frame(fist, current_time=100.0)
        self.assertEqual(res1.gesture_name, "FIST")

        # Frame 2: t=0.5 (still holding)
        res2 = self.classifier.process_frame(fist, current_time=100.5)
        self.assertEqual(res2.gesture_name, "FIST")

        # Frame 3: t=101.1 (hold duration > 1.0s)
        res3 = self.classifier.process_frame(fist, current_time=101.1)
        self.assertEqual(res3.gesture_name, "FIST_TOGGLE")

    def test_steady_open_palm_triggers_play_pause(self) -> None:
        """Verify holding an Open Palm steady for ~0.5s triggers OPEN_PALM_STEADY."""
        palm = make_open_palm_landmarks()

        # Hold stationary at x=0.5
        self.classifier.process_frame(palm, current_time=200.0)
        self.classifier.process_frame(palm, current_time=200.2)
        self.classifier.process_frame(palm, current_time=200.4)

        # At t=200.55 (> 0.5s steady)
        res = self.classifier.process_frame(palm, current_time=200.55)
        self.assertEqual(res.gesture_name, "OPEN_PALM_STEADY")

    def test_fast_moving_open_palm_triggers_swipe_not_play_pause(self) -> None:
        """Verify fast horizontal movement with open palm triggers SWIPE, not Play/Pause."""
        # Moving rapidly right: x=0.2 -> 0.35 -> 0.55 -> 0.75 within 0.2s
        p1 = make_open_palm_landmarks(x_center=0.2)
        p2 = make_open_palm_landmarks(x_center=0.4)
        p3 = make_open_palm_landmarks(x_center=0.6)
        p4 = make_open_palm_landmarks(x_center=0.8)

        self.classifier.process_frame(p1, current_time=300.0)
        self.classifier.process_frame(p2, current_time=300.05)
        self.classifier.process_frame(p3, current_time=300.10)
        res = self.classifier.process_frame(p4, current_time=300.15)

        self.assertEqual(res.gesture_name, "SWIPE_RIGHT")
        self.assertNotEqual(res.gesture_name, "OPEN_PALM_STEADY")

    def test_two_finger_moving_right_triggers_forward(self) -> None:
        """Verify two fingers moving right triggers TWO_FINGER_RIGHT (forward 10s)."""
        t1 = make_two_fingers_landmarks(x_center=0.3)
        t2 = make_two_fingers_landmarks(x_center=0.45)
        t3 = make_two_fingers_landmarks(x_center=0.60)

        self.classifier.process_frame(t1, current_time=400.0)
        self.classifier.process_frame(t2, current_time=400.05)
        res = self.classifier.process_frame(t3, current_time=400.10)

        self.assertEqual(res.gesture_name, "TWO_FINGER_RIGHT")

    def test_two_finger_moving_left_triggers_rewind(self) -> None:
        """Verify two fingers moving left triggers TWO_FINGER_LEFT (rewind 10s)."""
        t1 = make_two_fingers_landmarks(x_center=0.7)
        t2 = make_two_fingers_landmarks(x_center=0.55)
        t3 = make_two_fingers_landmarks(x_center=0.40)

        self.classifier.process_frame(t1, current_time=500.0)
        self.classifier.process_frame(t2, current_time=500.05)
        res = self.classifier.process_frame(t3, current_time=500.10)

        self.assertEqual(res.gesture_name, "TWO_FINGER_LEFT")

    def test_one_finger_scrolling_rules(self) -> None:
        """Verify one finger moving upward scrolls page down; downward scrolls page up."""
        # 1. Moving upward: y decreases from 0.6 -> 0.45 -> 0.30
        u1 = make_one_finger_landmarks(y_center=0.6)
        u2 = make_one_finger_landmarks(y_center=0.45)
        u3 = make_one_finger_landmarks(y_center=0.30)

        self.classifier.process_frame(u1, current_time=600.0)
        self.classifier.process_frame(u2, current_time=600.05)
        res_up = self.classifier.process_frame(u3, current_time=600.10)
        self.assertEqual(res_up.gesture_name, "ONE_FINGER_UP")
        self.assertTrue(res_up.is_continuous)

        # 2. Moving downward: y increases from 0.3 -> 0.45 -> 0.60
        self.classifier.reset()
        d1 = make_one_finger_landmarks(y_center=0.3)
        d2 = make_one_finger_landmarks(y_center=0.45)
        d3 = make_one_finger_landmarks(y_center=0.60)

        self.classifier.process_frame(d1, current_time=601.0)
        self.classifier.process_frame(d2, current_time=601.05)
        res_down = self.classifier.process_frame(d3, current_time=601.10)
        self.assertEqual(res_down.gesture_name, "ONE_FINGER_DOWN")
        self.assertTrue(res_down.is_continuous)

    def test_pinch_out_and_in_zoom(self) -> None:
        """Verify pinch distance increasing triggers PINCH_OUT (zoom in) and decreasing triggers PINCH_IN (zoom out)."""
        # 1. Pinch Out: distance increases from 0.03 -> 0.05 -> 0.08
        lm1 = make_pinch_landmarks(thumb_tip=(0.5, 0.5), index_tip=(0.53, 0.5))  # dist 0.03
        lm2 = make_pinch_landmarks(thumb_tip=(0.5, 0.5), index_tip=(0.55, 0.5))  # dist 0.05
        lm3 = make_pinch_landmarks(thumb_tip=(0.5, 0.5), index_tip=(0.58, 0.5))  # dist 0.08

        self.classifier.process_frame(lm1, current_time=700.0)
        self.classifier.process_frame(lm2, current_time=700.05)
        res_out = self.classifier.process_frame(lm3, current_time=700.10)
        self.assertEqual(res_out.gesture_name, "PINCH_OUT")
        self.assertTrue(res_out.is_continuous)

        # 2. Pinch In: distance decreases from 0.10 -> 0.07 -> 0.05
        self.classifier.reset()
        lm_in1 = make_pinch_landmarks(thumb_tip=(0.5, 0.5), index_tip=(0.60, 0.5)) # dist 0.10
        lm_in2 = make_pinch_landmarks(thumb_tip=(0.5, 0.5), index_tip=(0.57, 0.5)) # dist 0.07
        lm_in3 = make_pinch_landmarks(thumb_tip=(0.5, 0.5), index_tip=(0.55, 0.5)) # dist 0.05

        self.classifier.process_frame(lm_in1, current_time=701.0)
        self.classifier.process_frame(lm_in2, current_time=701.05)
        res_in = self.classifier.process_frame(lm_in3, current_time=701.10)
        self.assertEqual(res_in.gesture_name, "PINCH_IN")
        self.assertTrue(res_in.is_continuous)


if __name__ == "__main__":
    unittest.main()
