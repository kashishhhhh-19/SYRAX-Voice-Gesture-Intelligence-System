"""
gesture/gesture_classifier.py - Pure Landmark Gesture Classifier for SYRAX
Contains pure functions operating on 21 normalized hand landmark coordinates.
Includes stateful tracking for fist hold, steady open-palm play/pause, velocity swipes,
two-finger forward/rewind, one-finger scrolling, and pinch zooming.
Fully unit-testable without camera or GUI dependencies.
"""

import math
import time
from collections import deque
from dataclasses import dataclass
from typing import Deque, List, Optional, Tuple

import config


# Landmark topology constants
WRIST = 0
THUMB_CMC = 1
THUMB_MCP = 2
THUMB_IP = 3
THUMB_TIP = 4

INDEX_MCP = 5
INDEX_PIP = 6
INDEX_DIP = 7
INDEX_TIP = 8

MIDDLE_MCP = 9
MIDDLE_PIP = 10
MIDDLE_DIP = 11
MIDDLE_TIP = 12

RING_MCP = 13
RING_PIP = 14
RING_DIP = 15
RING_TIP = 16

PINKY_MCP = 17
PINKY_PIP = 18
PINKY_DIP = 19
PINKY_TIP = 20


@dataclass
class GestureClassificationResult:
    """Structured output from gesture classification."""
    gesture_name: str
    confidence: float
    is_continuous: bool = False
    hold_duration: float = 0.0
    speed: float = 0.0
    raw_pose: str = "NONE"


def get_euclidean_distance(p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
    """Calculate Euclidean distance between two 2D points."""
    return math.hypot(p1[0] - p2[0], p1[1] - p2[1])


def get_pinch_distance(landmarks: List[Tuple[float, float]]) -> float:
    """Calculate normalized distance between thumb tip and index tip."""
    if len(landmarks) < 21:
        return 1.0
    return get_euclidean_distance(landmarks[THUMB_TIP], landmarks[INDEX_TIP])


def is_finger_extended(
    landmarks: List[Tuple[float, float]],
    tip_idx: int,
    pip_idx: int,
    mcp_idx: int,
    wrist_idx: int = WRIST
) -> bool:
    """
    Determine if a finger (index, middle, ring, pinky) is extended away from palm.
    Accounts for both vertical Y position and distance from wrist.
    """
    if len(landmarks) < 21:
        return False
    tip = landmarks[tip_idx]
    pip = landmarks[pip_idx]
    mcp = landmarks[mcp_idx]
    wrist = landmarks[wrist_idx]

    dist_tip_wrist = get_euclidean_distance(tip, wrist)
    dist_pip_wrist = get_euclidean_distance(pip, wrist)
    dist_mcp_wrist = get_euclidean_distance(mcp, wrist)

    # Inverted screen coordinates: smaller Y means higher on screen
    y_extended = tip[1] < (pip[1] - 0.015)
    dist_extended = (dist_tip_wrist > dist_pip_wrist * 1.15) and (dist_tip_wrist > dist_mcp_wrist * 1.25)

    return y_extended or dist_extended


def is_thumb_extended(landmarks: List[Tuple[float, float]]) -> bool:
    """Determine if thumb is extended away from index base."""
    if len(landmarks) < 21:
        return False
    thumb_tip = landmarks[THUMB_TIP]
    index_mcp = landmarks[INDEX_MCP]
    wrist = landmarks[WRIST]

    dist_thumb_mcp = get_euclidean_distance(thumb_tip, index_mcp)
    dist_thumb_wrist = get_euclidean_distance(thumb_tip, wrist)
    return dist_thumb_mcp > 0.09 and dist_thumb_wrist > 0.15


def is_fist(landmarks: List[Tuple[float, float]]) -> Tuple[bool, float]:
    """
    Check if hand forms a Fist (all 4 fingers curled, thumb tucked in).
    Returns (is_fist, confidence).
    """
    if len(landmarks) < 21:
        return False, 0.0

    idx_ext = is_finger_extended(landmarks, INDEX_TIP, INDEX_PIP, INDEX_MCP)
    mid_ext = is_finger_extended(landmarks, MIDDLE_TIP, MIDDLE_PIP, MIDDLE_MCP)
    ring_ext = is_finger_extended(landmarks, RING_TIP, RING_PIP, RING_MCP)
    pinky_ext = is_finger_extended(landmarks, PINKY_TIP, PINKY_PIP, PINKY_MCP)
    thumb_ext = is_thumb_extended(landmarks)

    extended_count = sum([idx_ext, mid_ext, ring_ext, pinky_ext, thumb_ext])

    if extended_count == 0:
        return True, 0.95
    elif extended_count == 1 and thumb_ext:
        # Fist with thumb resting on outer fingers
        return True, 0.85
    return False, 0.0


def is_open_palm(landmarks: List[Tuple[float, float]]) -> Tuple[bool, float]:
    """
    Check if hand forms an Open Palm (all fingers extended and spread).
    Returns (is_open_palm, confidence).
    """
    if len(landmarks) < 21:
        return False, 0.0

    idx_ext = is_finger_extended(landmarks, INDEX_TIP, INDEX_PIP, INDEX_MCP)
    mid_ext = is_finger_extended(landmarks, MIDDLE_TIP, MIDDLE_PIP, MIDDLE_MCP)
    ring_ext = is_finger_extended(landmarks, RING_TIP, RING_PIP, RING_MCP)
    pinky_ext = is_finger_extended(landmarks, PINKY_TIP, PINKY_PIP, PINKY_MCP)
    thumb_ext = is_thumb_extended(landmarks)

    extended_count = sum([idx_ext, mid_ext, ring_ext, pinky_ext, thumb_ext])

    if extended_count >= 4 and idx_ext and mid_ext:
        conf = 0.95 if extended_count == 5 else 0.85
        return True, conf
    return False, 0.0


def is_two_fingers(landmarks: List[Tuple[float, float]]) -> Tuple[bool, float]:
    """
    Check if hand shows Two Fingers (Index + Middle extended, Ring + Pinky curled).
    Used for YouTube forward / rewind and play/pause.
    Returns (is_two_fingers, confidence).
    """
    if len(landmarks) < 21:
        return False, 0.0

    idx_ext = is_finger_extended(landmarks, INDEX_TIP, INDEX_PIP, INDEX_MCP)
    mid_ext = is_finger_extended(landmarks, MIDDLE_TIP, MIDDLE_PIP, MIDDLE_MCP)
    ring_ext = is_finger_extended(landmarks, RING_TIP, RING_PIP, RING_MCP)
    pinky_ext = is_finger_extended(landmarks, PINKY_TIP, PINKY_PIP, PINKY_MCP)

    if idx_ext and mid_ext and not ring_ext and not pinky_ext:
        return True, 0.92
    return False, 0.0


def is_one_finger(landmarks: List[Tuple[float, float]]) -> Tuple[bool, float]:
    """
    Check if hand shows One Finger (Index extended only, Middle/Ring/Pinky curled).
    Used for YouTube page scrolling.
    Returns (is_one_finger, confidence).
    """
    if len(landmarks) < 21:
        return False, 0.0

    idx_ext = is_finger_extended(landmarks, INDEX_TIP, INDEX_PIP, INDEX_MCP)
    mid_ext = is_finger_extended(landmarks, MIDDLE_TIP, MIDDLE_PIP, MIDDLE_MCP)
    ring_ext = is_finger_extended(landmarks, RING_TIP, RING_PIP, RING_MCP)
    pinky_ext = is_finger_extended(landmarks, PINKY_TIP, PINKY_PIP, PINKY_MCP)

    if idx_ext and not mid_ext and not ring_ext and not pinky_ext:
        return True, 0.90
    return False, 0.0


def classify_pose(landmarks: List[Tuple[float, float]]) -> Tuple[str, float]:
    """
    Classify static hand geometry into a primary pose.
    Pure function on landmark data.
    """
    if len(landmarks) < 21:
        return "NONE", 0.0

    # 1. Fist Check First (in a fist, fingers are curled, not pinching)
    fist_ok, fist_conf = is_fist(landmarks)
    if fist_ok:
        return "FIST", fist_conf

    # 2. Pinch Check (thumb tip close to index tip, but not curled into a fist)
    pinch_dist = get_pinch_distance(landmarks)
    if pinch_dist < config.PINCH_THRESHOLD:
        return "PINCH", 0.90

    # 3. Two Fingers Check
    two_ok, two_conf = is_two_fingers(landmarks)
    if two_ok:
        return "TWO_FINGERS", two_conf

    # 4. One Finger Check
    one_ok, one_conf = is_one_finger(landmarks)
    if one_ok:
        return "ONE_FINGER", one_conf

    # 5. Open Palm Check
    palm_ok, palm_conf = is_open_palm(landmarks)
    if palm_ok:
        return "OPEN_PALM", palm_conf

    return "UNKNOWN", 0.30


class GestureClassifier:
    """
    Temporal gesture classifier with smoothing, hold duration tracking,
    velocity swipe detection, and debounce cooldowns.
    """

    def __init__(self) -> None:
        # History buffers for temporal analysis
        self._pose_history: Deque[str] = deque(maxlen=config.SMOOTHING_WINDOW_SIZE)
        self._centroid_history: Deque[Tuple[float, float, float]] = deque(maxlen=12) # (x, y, timestamp)
        self._pinch_distance_history: Deque[Tuple[float, float]] = deque(maxlen=8)   # (distance, timestamp)

        # Hold tracking
        self._current_held_pose: Optional[str] = None
        self._pose_start_time: float = 0.0

        # Cooldown timestamps
        self._last_trigger_times: dict[str, float] = {}

    def reset(self, include_cooldowns: bool = False) -> None:
        """Clear historical buffers and timers. Optionally clear cooldown timers."""
        self._pose_history.clear()
        self._centroid_history.clear()
        self._pinch_distance_history.clear()
        self._current_held_pose = None
        self._pose_start_time = 0.0
        if include_cooldowns:
            self._last_trigger_times.clear()

    def is_cooling_down(self, gesture: str, cooldown_seconds: float, now: float) -> bool:
        """Return True if gesture was triggered within cooldown period."""
        last = self._last_trigger_times.get(gesture, 0.0)
        return (now - last) < cooldown_seconds

    def record_trigger(self, gesture: str, now: float) -> None:
        """Record timestamp of executed gesture."""
        self._last_trigger_times[gesture] = now

    def process_frame(
        self,
        landmarks: Optional[List[Tuple[float, float]]],
        current_time: Optional[float] = None
    ) -> GestureClassificationResult:
        """
        Process single video frame landmarks through temporal classification rules.
        Pure landmark coordinates in; structured GestureClassificationResult out.
        """
        now = current_time if current_time is not None else time.time()

        if not landmarks or len(landmarks) < 21:
            self.reset()
            return GestureClassificationResult("NONE", 0.0)

        # 1. Classify raw static pose
        raw_pose, pose_conf = classify_pose(landmarks)
        self._pose_history.append(raw_pose)

        # Majority vote smoothing over recent window
        smoothed_pose = max(set(self._pose_history), key=self._pose_history.count)

        # 2. Track Centroid Movement & Speed
        wrist = landmarks[WRIST]
        cx, cy = wrist[0], wrist[1]
        self._centroid_history.append((cx, cy, now))

        # Calculate movement speed and velocities over recent frames
        speed = 0.0
        vx = 0.0
        vy = 0.0
        if len(self._centroid_history) >= 3:
            p_old = self._centroid_history[0]
            p_new = self._centroid_history[-1]
            dt = max(0.001, p_new[2] - p_old[2])
            vx = (p_new[0] - p_old[0]) / dt
            vy = (p_new[1] - p_old[1]) / dt
            speed = math.hypot(p_new[0] - p_old[0], p_new[1] - p_old[1]) / dt

        # 3. Track Pose Hold Duration
        if smoothed_pose == self._current_held_pose:
            hold_duration = now - self._pose_start_time
        else:
            self._current_held_pose = smoothed_pose
            self._pose_start_time = now
            hold_duration = 0.0

        # ======================================================================
        # GESTURE EVALUATION LOGIC
        # ======================================================================

        # RULE A: Fist Hold (~1.0s) -> Toggles Gesture Mode ON/OFF
        if smoothed_pose == "FIST":
            if hold_duration >= config.FIST_HOLD_DURATION_SECONDS:
                if not self.is_cooling_down("FIST_TOGGLE", config.FIST_TOGGLE_COOLDOWN_SECONDS, now):
                    self.record_trigger("FIST_TOGGLE", now)
                    # Reset hold timer after toggle
                    self._pose_start_time = now
                    return GestureClassificationResult(
                        gesture_name="FIST_TOGGLE",
                        confidence=0.95,
                        hold_duration=hold_duration,
                        speed=speed,
                        raw_pose="FIST"
                    )
            return GestureClassificationResult(
                gesture_name="FIST",
                confidence=pose_conf,
                hold_duration=hold_duration,
                speed=speed,
                raw_pose="FIST"
            )

        # RULE B: Swipes (Swipe Right -> Next Video; Swipe Left -> Previous Video)
        # Fast horizontal hand motion (speed > threshold)
        if len(self._centroid_history) >= 4 and abs(vx) > (config.SWIPE_VELOCITY_THRESHOLD * 8):
            if vx > 0 and not self.is_cooling_down("SWIPE_RIGHT", config.SWIPE_COOLDOWN_SECONDS, now):
                self.record_trigger("SWIPE_RIGHT", now)
                self._centroid_history.clear()
                return GestureClassificationResult(
                    gesture_name="SWIPE_RIGHT",
                    confidence=0.92,
                    speed=speed,
                    raw_pose=smoothed_pose
                )
            elif vx < 0 and not self.is_cooling_down("SWIPE_LEFT", config.SWIPE_COOLDOWN_SECONDS, now):
                self.record_trigger("SWIPE_LEFT", now)
                self._centroid_history.clear()
                return GestureClassificationResult(
                    gesture_name="SWIPE_LEFT",
                    confidence=0.92,
                    speed=speed,
                    raw_pose=smoothed_pose
                )

        # RULE C: Open Palm Steady (~0.5s) -> Play/Pause ("k")
        # Critical condition: Open Palm must NOT trigger when hand is moving fast (that is a swipe)
        if smoothed_pose == "OPEN_PALM":
            is_steady = speed < (config.PALM_MAX_MOVEMENT_SPEED * 8)
            if is_steady and hold_duration >= config.OPEN_PALM_STEADY_DURATION_SECONDS:
                if not self.is_cooling_down("OPEN_PALM_STEADY", config.GESTURE_COOLDOWN_SECONDS, now):
                    self.record_trigger("OPEN_PALM_STEADY", now)
                    self._pose_start_time = now  # Reset hold duration after triggering
                    return GestureClassificationResult(
                        gesture_name="OPEN_PALM_STEADY",
                        confidence=0.94,
                        hold_duration=hold_duration,
                        speed=speed,
                        raw_pose="OPEN_PALM"
                    )
            return GestureClassificationResult(
                gesture_name="OPEN_PALM",
                confidence=pose_conf,
                hold_duration=hold_duration,
                speed=speed,
                raw_pose="OPEN_PALM"
            )

        # RULE D: Two-Finger Gestures (Forward / Rewind)
        if smoothed_pose == "TWO_FINGERS":
            # Two fingers moving right -> Forward video 10s ("l")
            if vx > (config.TWO_FINGER_VELOCITY_THRESHOLD * 6):
                if not self.is_cooling_down("TWO_FINGER_RIGHT", config.TWO_FINGER_COOLDOWN_SECONDS, now):
                    self.record_trigger("TWO_FINGER_RIGHT", now)
                    return GestureClassificationResult(
                        gesture_name="TWO_FINGER_RIGHT",
                        confidence=0.90,
                        speed=speed,
                        raw_pose="TWO_FINGERS"
                    )
            # Two fingers moving left -> Rewind video 10s ("j")
            elif vx < -(config.TWO_FINGER_VELOCITY_THRESHOLD * 6):
                if not self.is_cooling_down("TWO_FINGER_LEFT", config.TWO_FINGER_COOLDOWN_SECONDS, now):
                    self.record_trigger("TWO_FINGER_LEFT", now)
                    return GestureClassificationResult(
                        gesture_name="TWO_FINGER_LEFT",
                        confidence=0.90,
                        speed=speed,
                        raw_pose="TWO_FINGERS"
                    )
            return GestureClassificationResult(
                gesture_name="TWO_FINGERS",
                confidence=pose_conf,
                hold_duration=hold_duration,
                speed=speed,
                raw_pose="TWO_FINGERS"
            )

        # Track Pinch Distance for Zooming Gestures
        pinch_dist = get_pinch_distance(landmarks)
        self._pinch_distance_history.append((pinch_dist, now))

        # RULE E: Pinch Zoom (Pinch Out -> Zoom In; Pinch In -> Zoom Out)
        if len(self._pinch_distance_history) >= 3 and (
            smoothed_pose in ("PINCH", "ONE_FINGER", "UNKNOWN") or pinch_dist < 0.14
        ):
            old_dist = self._pinch_distance_history[0][0]
            new_dist = self._pinch_distance_history[-1][0]
            dist_delta = new_dist - old_dist

            if abs(dist_delta) > config.PINCH_DISTANCE_DELTA_THRESHOLD:
                if not self.is_cooling_down("PINCH_ZOOM", config.PINCH_REPEAT_INTERVAL, now):
                    self.record_trigger("PINCH_ZOOM", now)
                    self._pinch_distance_history.clear()
                    if dist_delta > 0:
                        # Distance increasing -> Pinch Out -> Zoom In (Ctrl + plus)
                        return GestureClassificationResult(
                            gesture_name="PINCH_OUT",
                            confidence=0.88,
                            is_continuous=True,
                            speed=speed,
                            raw_pose="PINCH"
                        )
                    else:
                        # Distance decreasing -> Pinch In -> Zoom Out (Ctrl + minus)
                        return GestureClassificationResult(
                            gesture_name="PINCH_IN",
                            confidence=0.88,
                            is_continuous=True,
                            speed=speed,
                            raw_pose="PINCH"
                        )

        # RULE F: One-Finger Scrolling (Page Navigation)
        if smoothed_pose == "ONE_FINGER":
            if not self.is_cooling_down("SCROLL", config.SCROLL_REPEAT_INTERVAL, now):
                # User requirement:
                # - One finger moving upward -> Scroll page down
                # - One finger moving downward -> Scroll page up
                if vy < -0.15:  # Moving upward on screen
                    self.record_trigger("SCROLL", now)
                    return GestureClassificationResult(
                        gesture_name="ONE_FINGER_UP",
                        confidence=0.91,
                        is_continuous=True,
                        speed=speed,
                        raw_pose="ONE_FINGER"
                    )
                elif vy > 0.15:  # Moving downward on screen
                    self.record_trigger("SCROLL", now)
                    return GestureClassificationResult(
                        gesture_name="ONE_FINGER_DOWN",
                        confidence=0.91,
                        is_continuous=True,
                        speed=speed,
                        raw_pose="ONE_FINGER"
                    )
            return GestureClassificationResult(
                gesture_name="ONE_FINGER",
                confidence=pose_conf,
                hold_duration=hold_duration,
                speed=speed,
                raw_pose="ONE_FINGER"
            )

        return GestureClassificationResult(
            gesture_name=smoothed_pose,
            confidence=pose_conf,
            hold_duration=hold_duration,
            speed=speed,
            raw_pose=smoothed_pose
        )
