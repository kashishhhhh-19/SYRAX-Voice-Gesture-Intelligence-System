"""
GestureFlow - Gesture Recognition Module
Classifies hand landmarks into gestures: Fist, Open Palm, Pointing Up,
Pointing Down, Swipe Left, Swipe Right, and Pinch Out.
Includes temporal stabilization, motion velocity tracking, and debouncing.
"""

import math
import time
from collections import deque
from enum import Enum
from typing import Deque, Dict, List, Optional, Tuple

from app.config import GestureThresholds, CooldownConfig
from app.hand_tracking import (
    HandData, LandmarkPoint,
    WRIST, THUMB_CMC, THUMB_MCP, THUMB_IP, THUMB_TIP,
    INDEX_FINGER_MCP, INDEX_FINGER_PIP, INDEX_FINGER_DIP, INDEX_FINGER_TIP,
    MIDDLE_FINGER_MCP, MIDDLE_FINGER_PIP, MIDDLE_FINGER_DIP, MIDDLE_FINGER_TIP,
    RING_FINGER_MCP, RING_FINGER_PIP, RING_FINGER_DIP, RING_FINGER_TIP,
    PINKY_MCP, PINKY_PIP, PINKY_DIP, PINKY_TIP
)


class GestureType(Enum):
    NONE = "None"
    FIST = "Fist"
    OPEN_PALM = "Open Palm"
    POINTING_UP = "Pointing Up"
    POINTING_DOWN = "Pointing Down"
    SWIPE_RIGHT = "Swipe Right"
    SWIPE_LEFT = "Swipe Left"
    PINCH_OUT = "Pinch Out (Zoom In)"


from dataclasses import dataclass

@dataclass
class GestureResult:
    """Structured output for the recognized gesture at a specific frame."""
    gesture: GestureType
    confidence: float
    is_triggered: bool           # True on the exact frame the action should execute
    description: str             # Human-readable debug/status note
    cooldown_remaining: float    # Time in seconds before another action can trigger
    velocity: Tuple[float, float] = (0.0, 0.0) # (vx, vy) normalized per second
    displacement: Tuple[float, float] = (0.0, 0.0)


class MotionHistory:
    """
    Sliding window buffer of palm center positions and timestamps.
    Computes velocity, net displacement, and differentiates motion from stationary jitter.
    """

    def __init__(self, max_frames: int = 12):
        self.max_frames = max_frames
        self.buffer: Deque[Tuple[float, float, float]] = deque(maxlen=max_frames) # (time, x, y)
        self.pinch_buffer: Deque[Tuple[float, float]] = deque(maxlen=max_frames)  # (time, pinch_dist)

    def append(self, timestamp: float, x: float, y: float, pinch_dist: Optional[float] = None):
        self.buffer.append((timestamp, x, y))
        if pinch_dist is not None:
            self.pinch_buffer.append((timestamp, pinch_dist))

    def clear(self):
        self.buffer.clear()
        self.pinch_buffer.clear()

    def get_metrics(self) -> Tuple[float, float, float, float]:
        """
        Returns (dx, dy, vx, vy):
        - dx, dy: net displacement over the sliding window.
        - vx, vy: normalized velocity (units / sec).
        """
        if len(self.buffer) < 3:
            return 0.0, 0.0, 0.0, 0.0

        t0, x0, y0 = self.buffer[0]
        t1, x1, y1 = self.buffer[-1]
        dt = t1 - t0

        if dt <= 0.01:
            return 0.0, 0.0, 0.0, 0.0

        dx = x1 - x0
        dy = y1 - y0
        vx = dx / dt
        vy = dy / dt

        return dx, dy, vx, vy

    def get_pinch_delta(self) -> float:
        """Returns the change in pinch distance over recent frames."""
        if len(self.pinch_buffer) < 3:
            return 0.0
        return self.pinch_buffer[-1][1] - self.pinch_buffer[0][1]


class GestureRecognizer:
    """
    Robust geometric classifier for MediaPipe hand landmarks.
    Enforces temporal stability for static postures, velocity thresholds for swipes,
    and distinct cooldowns for every gesture action.
    """

    def __init__(
        self,
        thresholds: Optional[GestureThresholds] = None,
        cooldowns: Optional[CooldownConfig] = None
    ):
        self.thresholds = thresholds or GestureThresholds()
        self.cooldowns = cooldowns or CooldownConfig()

        self.motion_history = MotionHistory(self.thresholds.swipe_history_frames)
        self.last_action_time: Dict[GestureType, float] = {}
        self.global_cooldown_until: float = 0.0

        # Frame stability tracking for static postures
        self._candidate_gesture: GestureType = GestureType.NONE
        self._candidate_count: int = 0
        self._last_active_gesture: GestureType = GestureType.NONE

    def reset(self):
        """Resets all buffers and cooldown timers."""
        self.motion_history.clear()
        self.last_action_time.clear()
        self.global_cooldown_until = 0.0
        self._candidate_gesture = GestureType.NONE
        self._candidate_count = 0
        self._last_active_gesture = GestureType.NONE

    def recognize(self, hands: List[HandData], current_time: Optional[float] = None) -> GestureResult:
        """
        Primary recognition pipeline.
        Processes primary hand data, analyzes geometry and motion, and applies debouncing.
        """
        now = time.time() if current_time is None else current_time

        # If no hand detected, clear motion history and decay candidates
        if not hands or len(hands) == 0:
            self.motion_history.clear()
            self._candidate_count = max(0, self._candidate_count - 1)
            rem = max(0.0, self.global_cooldown_until - now)
            return GestureResult(
                gesture=GestureType.NONE,
                confidence=0.0,
                is_triggered=False,
                description="No hand visible",
                cooldown_remaining=round(rem, 2)
            )

        # Use primary hand (first detected hand)
        hand = hands[0]
        lm = hand.landmarks
        if len(lm) < 21:
            return GestureResult(
                gesture=GestureType.NONE,
                confidence=0.0,
                is_triggered=False,
                description="Incomplete landmarks",
                cooldown_remaining=0.0
            )

        cx, cy = hand.palm_center_norm
        scale = hand.hand_scale

        # Calculate current pinch distance (Thumb Tip to Index Tip normalized by hand scale)
        raw_pinch_dist = math.hypot(lm[THUMB_TIP].x - lm[INDEX_FINGER_TIP].x, lm[THUMB_TIP].y - lm[INDEX_FINGER_TIP].y)
        normalized_pinch = raw_pinch_dist / scale
        self.motion_history.append(now, cx, cy, normalized_pinch)

        dx, dy, vx, vy = self.motion_history.get_metrics()
        pinch_delta = self.motion_history.get_pinch_delta()

        # 1. Analyze finger extension states
        extended = self._get_finger_extensions(lm, scale)

        # 2. Check for dynamic motion gestures first (Swipe, Pinch-out)
        dynamic_gesture, dynamic_conf, dynamic_desc = self._classify_motion_gesture(
            extended, dx, dy, vx, vy, normalized_pinch, pinch_delta, hands
        )

        raw_gesture = GestureType.NONE
        confidence = 0.0
        description = ""

        if dynamic_gesture != GestureType.NONE:
            raw_gesture = dynamic_gesture
            confidence = dynamic_conf
            description = dynamic_desc
        else:
            # 3. Classify static posture (only when hand is not moving at swipe speeds)
            speed = math.hypot(vx, vy)
            if speed < (self.thresholds.swipe_min_velocity * 0.75):
                static_gesture, static_conf, static_desc = self._classify_static_gesture(extended, lm, scale)
                raw_gesture = static_gesture
                confidence = static_conf
                description = static_desc
            else:
                raw_gesture = GestureType.NONE
                confidence = 0.0
                description = "Hand in motion"

        # 4. Temporal Stabilization and Debouncing
        return self._stabilize_and_debounce(raw_gesture, confidence, description, now, (vx, vy), (dx, dy))

    def _get_finger_extensions(self, lm: List[LandmarkPoint], scale: float) -> Dict[str, bool]:
        """
        Determines whether each finger (thumb, index, middle, ring, pinky) is extended or curled.
        Uses scale-normalized Euclidean distances from MCP base knuckle to tip vs MCP to PIP.
        Works consistently in any hand orientation (upward, downward, tilted).
        """
        def is_finger_extended(tip_idx: int, pip_idx: int, mcp_idx: int) -> bool:
            dist_tip_mcp = math.hypot(lm[tip_idx].x - lm[mcp_idx].x, lm[tip_idx].y - lm[mcp_idx].y)
            dist_pip_mcp = math.hypot(lm[pip_idx].x - lm[mcp_idx].x, lm[pip_idx].y - lm[mcp_idx].y)
            ratio = dist_tip_mcp / max(dist_pip_mcp, 0.01)
            return ratio >= 1.60

        index_ext = is_finger_extended(INDEX_FINGER_TIP, INDEX_FINGER_PIP, INDEX_FINGER_MCP)
        middle_ext = is_finger_extended(MIDDLE_FINGER_TIP, MIDDLE_FINGER_PIP, MIDDLE_FINGER_MCP)
        ring_ext = is_finger_extended(RING_FINGER_TIP, RING_FINGER_PIP, RING_FINGER_MCP)
        pinky_ext = is_finger_extended(PINKY_TIP, PINKY_PIP, PINKY_MCP)

        # Thumb extension: distance from thumb tip to pinky MCP compared to IP to pinky MCP
        thumb_tip_dist = math.hypot(lm[THUMB_TIP].x - lm[PINKY_MCP].x, lm[THUMB_TIP].y - lm[PINKY_MCP].y)
        thumb_ip_dist = math.hypot(lm[THUMB_IP].x - lm[PINKY_MCP].x, lm[THUMB_IP].y - lm[PINKY_MCP].y)
        thumb_ext = thumb_tip_dist > (thumb_ip_dist * 1.15)

        return {
            "thumb": thumb_ext,
            "index": index_ext,
            "middle": middle_ext,
            "ring": ring_ext,
            "pinky": pinky_ext
        }

    def _classify_motion_gesture(
        self,
        extended: Dict[str, bool],
        dx: float,
        dy: float,
        vx: float,
        vy: float,
        normalized_pinch: float,
        pinch_delta: float,
        hands: List[HandData]
    ) -> Tuple[GestureType, float, str]:
        """Classifies high-speed directional motion gestures (Swipes, Pinch-out / Zoom)."""
        th = self.thresholds

        # Two-Hand Zoom In: Two hands moving apart
        if len(hands) >= 2:
            h1_x, h1_y = hands[0].palm_center_norm
            h2_x, h2_y = hands[1].palm_center_norm
            two_hand_dist = math.hypot(h2_x - h1_x, h2_y - h1_y)
            if two_hand_dist > 0.40:
                return GestureType.PINCH_OUT, 0.95, f"Two-Hand Zoom In (dist: {two_hand_dist:.2f})"

        # Single-Hand Pinch-out / Zoom In:
        # Both thumb and index must be extended/active, other fingers curled, and pinch distance expanding
        thumb_and_index_active = extended["thumb"] and extended["index"]
        if thumb_and_index_active and not extended["ring"] and not extended["pinky"]:
            if pinch_delta >= th.pinch_spread_delta or normalized_pinch >= th.pinch_out_distance:
                return GestureType.PINCH_OUT, 0.88, f"Pinch Out (spread: {pinch_delta:+.2f}, pinch: {normalized_pinch:.2f})"

        # Swipe detection: Hand must be open/partially extended (not a tight fist)
        num_extended = sum(1 for k, v in extended.items() if v)
        if num_extended >= 2:
            # Swipe Right: dx > min_displacement, vx > min_velocity, dy drift within bounds
            if dx >= th.swipe_min_displacement_x and vx >= th.swipe_min_velocity and abs(dy) <= th.swipe_max_displacement_y:
                return GestureType.SWIPE_RIGHT, 0.92, f"Swipe Right (dx: {dx:+.2f}, vx: {vx:+.2f})"

            # Swipe Left: dx < -min_displacement, vx < -min_velocity, dy drift within bounds
            if dx <= -th.swipe_min_displacement_x and vx <= -th.swipe_min_velocity and abs(dy) <= th.swipe_max_displacement_y:
                return GestureType.SWIPE_LEFT, 0.92, f"Swipe Left (dx: {dx:+.2f}, vx: {vx:+.2f})"

        return GestureType.NONE, 0.0, ""

    def _classify_static_gesture(
        self,
        extended: Dict[str, bool],
        lm: List[LandmarkPoint],
        scale: float
    ) -> Tuple[GestureType, float, str]:
        """Classifies static posture: Fist, Open Palm, Pointing Up, Pointing Down."""
        th = self.thresholds

        num_extended = sum(1 for k, v in extended.items() if v)
        index_only = extended["index"] and not extended["middle"] and not extended["ring"] and not extended["pinky"]

        # 1. Fist: All 4 main fingers curled
        if not extended["index"] and not extended["middle"] and not extended["ring"] and not extended["pinky"]:
            return GestureType.FIST, 0.95, "Fist (Curled: All fingers)"

        # 2. Open Palm: All 5 fingers extended
        if extended["thumb"] and extended["index"] and extended["middle"] and extended["ring"] and extended["pinky"]:
            return GestureType.OPEN_PALM, 0.96, "Open Palm (Extended: All 5 fingers)"

        # Also accept 4 fingers extended without thumb for Open Palm if hand is wide
        if num_extended >= 4 and not index_only:
            return GestureType.OPEN_PALM, 0.85, f"Open Palm (Extended: {num_extended} fingers)"

        # 3. Single Index Finger Pointing (Up or Down)
        if index_only:
            # Compute index pointing vector from MCP to TIP
            dx = lm[INDEX_FINGER_TIP].x - lm[INDEX_FINGER_MCP].x
            dy = lm[INDEX_FINGER_TIP].y - lm[INDEX_FINGER_MCP].y
            length = math.hypot(dx, dy)

            if length > 0.05:
                # Angle in degrees relative to vertical (upward is -90 deg, downward is +90 deg in screen coords)
                angle_deg = math.degrees(math.atan2(dy, dx))

                # Upward: -90 +/- tolerance (-125 to -55)
                up_min = -90.0 - th.pointing_vertical_tolerance_deg
                up_max = -90.0 + th.pointing_vertical_tolerance_deg
                if up_min <= angle_deg <= up_max:
                    return GestureType.POINTING_UP, 0.94, f"Pointing Up (angle: {angle_deg:.1f}°)"

                # Downward: +90 +/- tolerance (55 to 125)
                down_min = 90.0 - th.pointing_vertical_tolerance_deg
                down_max = 90.0 + th.pointing_vertical_tolerance_deg
                if down_min <= angle_deg <= down_max:
                    return GestureType.POINTING_DOWN, 0.94, f"Pointing Down (angle: {angle_deg:.1f}°)"

        return GestureType.NONE, 0.0, "Undefined Hand Shape"

    def _stabilize_and_debounce(
        self,
        raw_gesture: GestureType,
        confidence: float,
        description: str,
        now: float,
        velocity: Tuple[float, float],
        displacement: Tuple[float, float]
    ) -> GestureResult:
        """
        Applies frame-stability filter for static postures and individual cooldowns
        to prevent accidental duplicate triggers.
        """
        # Determine cooldown required for this gesture
        cd_duration = self.cooldowns.default_cooldown
        if raw_gesture in (GestureType.SWIPE_RIGHT, GestureType.SWIPE_LEFT):
            cd_duration = self.cooldowns.swipe_cooldown
        elif raw_gesture == GestureType.PINCH_OUT:
            cd_duration = self.cooldowns.zoom_cooldown
        elif raw_gesture in (GestureType.POINTING_UP, GestureType.POINTING_DOWN):
            cd_duration = self.cooldowns.scroll_cooldown
        elif raw_gesture in (GestureType.FIST, GestureType.OPEN_PALM):
            cd_duration = self.cooldowns.mode_toggle_cooldown

        time_since_last = now - self.last_action_time.get(raw_gesture, 0.0)
        on_cooldown = (now < self.global_cooldown_until) or (time_since_last < cd_duration)
        cooldown_remaining = max(0.0, self.global_cooldown_until - now, cd_duration - time_since_last)

        # Dynamic motion gestures (Swipes, Pinch) trigger immediately when conditions are met
        is_motion_gesture = raw_gesture in (GestureType.SWIPE_RIGHT, GestureType.SWIPE_LEFT, GestureType.PINCH_OUT)

        should_trigger = False

        if is_motion_gesture:
            if not on_cooldown:
                should_trigger = True
                self.last_action_time[raw_gesture] = now
                self.global_cooldown_until = now + cd_duration
                self.motion_history.clear()  # Clear motion buffer so swipe doesn't re-trigger immediately
            confirmed_gesture = raw_gesture
        else:
            # Static postures require N consecutive frames
            if raw_gesture == self._candidate_gesture and raw_gesture != GestureType.NONE:
                self._candidate_count += 1
            else:
                self._candidate_gesture = raw_gesture
                self._candidate_count = 1

            if self._candidate_count >= self.thresholds.stability_required_frames:
                confirmed_gesture = raw_gesture
                # Trigger action if not on cooldown
                if not on_cooldown and (confirmed_gesture != self._last_active_gesture or raw_gesture in (GestureType.POINTING_UP, GestureType.POINTING_DOWN)):
                    should_trigger = True
                    self.last_action_time[raw_gesture] = now
                    self.global_cooldown_until = now + cd_duration
            else:
                confirmed_gesture = GestureType.NONE

        if confirmed_gesture != GestureType.NONE:
            self._last_active_gesture = confirmed_gesture

        return GestureResult(
            gesture=confirmed_gesture,
            confidence=confidence,
            is_triggered=should_trigger,
            description=description,
            cooldown_remaining=round(cooldown_remaining, 2),
            velocity=velocity,
            displacement=displacement
        )
