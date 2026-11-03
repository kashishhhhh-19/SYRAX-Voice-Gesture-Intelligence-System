"""
gesture/motion.py - Spatial Velocity, Directional Swipes, and Movement-Driven Scrolling
Maintains sliding-window trajectory buffers for palm center, index tip, and pinch distance.
Detects SWIPE_RIGHT, SWIPE_LEFT, SWIPE_UP, SWIPE_DOWN, PINCH_IN, PINCH_OUT,
and calculates smooth, rate-limited, movement-driven scroll deltas.
"""

import math
import time
from collections import deque
from dataclasses import dataclass
from typing import Deque, List, Optional, Tuple

from gesture.features import INDEX_TIP, MIDDLE_TIP, THUMB_TIP, get_normalized_pinch_distance


@dataclass
class MotionMetrics:
    """Displacement, velocity, and speed over sliding window."""
    dx: float
    dy: float
    vx: float
    vy: float
    speed: float
    duration: float


@dataclass
class MotionClassificationResult:
    """Output from dynamic motion analysis."""
    gesture: Optional[str]
    confidence: float
    description: str
    metrics: MotionMetrics
    scroll_delta: int = 0          # Continuous movement-driven scroll amount (0 if stationary)
    is_continuous: bool = False


class MotionTracker:
    """
    Sliding window tracker for hand trajectories, velocity vectors,
    pinch delta, and continuous fingertip displacement.
    """

    def __init__(
        self,
        window_ms: int = 400,
        swipe_min_distance: float = 0.12,
        swipe_min_velocity: float = 0.35,
        swipe_max_perpendicular_ratio: float = 0.55,
        pinch_spread_delta: float = 0.05,
        scroll_deadzone_dy: float = 0.015,
        scroll_sensitivity: float = 1200.0,
        max_scroll_tick_rate: int = 15,
        max_scroll_step: int = 360,
        invert_scroll: bool = False
    ) -> None:
        self.window_sec = window_ms / 1000.0
        self.swipe_min_distance = swipe_min_distance
        self.swipe_min_velocity = swipe_min_velocity
        self.swipe_max_perp_ratio = swipe_max_perpendicular_ratio
        self.pinch_spread_delta = pinch_spread_delta
        self.scroll_deadzone_dy = scroll_deadzone_dy
        self.scroll_sensitivity = scroll_sensitivity
        self.scroll_interval_sec = 1.0 / max(1, max_scroll_tick_rate)
        self.max_scroll_step = max_scroll_step
        self.invert_scroll = invert_scroll

        # Sliding window buffers: (timestamp, x, y)
        self._palm_buffer: Deque[Tuple[float, float, float]] = deque(maxlen=24)
        self._index_tip_buffer: Deque[Tuple[float, float, float]] = deque(maxlen=24)
        self._pinch_buffer: Deque[Tuple[float, float]] = deque(maxlen=24)  # (timestamp, pinch_dist)

        # Scrolling state
        self._last_scroll_time: float = 0.0
        self._last_scroll_y: Optional[float] = None

    def reset(self) -> None:
        """Clear motion buffers and scroll states."""
        self._palm_buffer.clear()
        self._index_tip_buffer.clear()
        self._pinch_buffer.clear()
        self._last_scroll_time = 0.0
        self._last_scroll_y = None

    def _prune_buffer(self, buf: Deque, now: float) -> None:
        """Discard samples older than window_sec."""
        cutoff = now - self.window_sec
        while buf and buf[0][0] < cutoff:
            buf.popleft()

    def _compute_metrics(self, buf: Deque[Tuple[float, float, float]]) -> MotionMetrics:
        """Calculate displacement, velocity, and speed across buffer."""
        if len(buf) < 2:
            return MotionMetrics(0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

        t0, x0, y0 = buf[0]
        t1, x1, y1 = buf[-1]
        dt = max(0.001, t1 - t0)

        dx = x1 - x0
        dy = y1 - y0
        vx = dx / dt
        vy = dy / dt
        speed = math.hypot(vx, vy)

        return MotionMetrics(dx, dy, vx, vy, speed, dt)

    def process_frame(
        self,
        landmarks: Optional[List[Tuple[float, float]]],
        static_pose: str,
        current_time: Optional[float] = None
    ) -> MotionClassificationResult:
        """
        Evaluate frame motion against sliding window history.
        Detects directional swipes, pinch expansion, and continuous scrolling.
        """
        now = time.time() if current_time is None else current_time

        if not landmarks or len(landmarks) < 21:
            self.reset()
            empty_m = MotionMetrics(0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
            return MotionClassificationResult(None, 0.0, "No hand visible", empty_m)

        # 1. Update Buffers
        from gesture.features import get_palm_center
        cx, cy = get_palm_center(landmarks)
        self._palm_buffer.append((now, cx, cy))
        self._prune_buffer(self._palm_buffer, now)

        idx_tip_x, idx_tip_y = landmarks[INDEX_TIP]
        self._index_tip_buffer.append((now, idx_tip_x, idx_tip_y))
        self._prune_buffer(self._index_tip_buffer, now)

        pinch_dist = get_normalized_pinch_distance(landmarks)
        self._pinch_buffer.append((now, pinch_dist))
        self._prune_buffer(self._pinch_buffer, now)

        palm_metrics = self._compute_metrics(self._palm_buffer)
        tip_metrics = self._compute_metrics(self._index_tip_buffer)

        # ======================================================================
        # 2. CONTINUOUS MOVEMENT-DRIVEN SCROLLING (ONE_FINGER)
        # ======================================================================
        if static_pose == "ONE_FINGER":
            scroll_delta = 0
            gesture_name = None

            if self._last_scroll_y is not None and (now - self._last_scroll_time) >= self.scroll_interval_sec:
                # Displaced distance of index fingertip since last tick
                delta_y = idx_tip_y - self._last_scroll_y

                # Dead-zone check: static finger produces ZERO scroll
                if abs(delta_y) > self.scroll_deadzone_dy:
                    # Invert logic:
                    # In screen coordinates, moving UP means delta_y is negative.
                    # Standard scroll: finger moving UP -> scroll UP (positive wheel delta).
                    direction_sign = 1 if delta_y < 0 else -1
                    if self.invert_scroll:
                        direction_sign = -direction_sign

                    # Proportional scroll magnitude capped at max_scroll_step
                    raw_amount = int(abs(delta_y) * self.scroll_sensitivity)
                    bounded_amount = min(self.max_scroll_step, max(60, raw_amount))
                    scroll_delta = direction_sign * bounded_amount

                    gesture_name = "ONE_FINGER_UP" if scroll_delta > 0 else "ONE_FINGER_DOWN"
                    self._last_scroll_time = now
                    self._last_scroll_y = idx_tip_y
            elif self._last_scroll_y is None:
                self._last_scroll_y = idx_tip_y
                self._last_scroll_time = now

            if scroll_delta != 0:
                return MotionClassificationResult(
                    gesture=gesture_name,
                    confidence=0.92,
                    description=f"Continuous Scroll: {scroll_delta:+d} ticks",
                    metrics=tip_metrics,
                    scroll_delta=scroll_delta,
                    is_continuous=True
                )
            else:
                return MotionClassificationResult(
                    gesture=None,
                    confidence=0.0,
                    description="One Finger Stationary (Dead-zone)",
                    metrics=tip_metrics,
                    scroll_delta=0
                )
        else:
            self._last_scroll_y = None

        # ======================================================================
        # 3. TWO-FINGER HORIZONTAL MOVEMENT (TWO_FINGERS)
        # ======================================================================
        if static_pose == "TWO_FINGERS":
            # Horizontal motion of fingertips
            mid_tip_x = landmarks[MIDDLE_TIP][0]
            avg_x = (idx_tip_x + mid_tip_x) / 2.0
            if abs(tip_metrics.dx) > 0.06 and abs(tip_metrics.vx) > 0.25:
                if tip_metrics.dx > 0:
                    return MotionClassificationResult(
                        gesture="TWO_FINGERS_RIGHT",
                        confidence=0.91,
                        description="Two Fingers Moving Right",
                        metrics=tip_metrics
                    )
                else:
                    return MotionClassificationResult(
                        gesture="TWO_FINGERS_LEFT",
                        confidence=0.91,
                        description="Two Fingers Moving Left",
                        metrics=tip_metrics
                    )

        # ======================================================================
        # 4. PINCH ZOOM IN / OUT
        # ======================================================================
        if len(self._pinch_buffer) >= 3 and static_pose in ("PINCH", "ONE_FINGER", "UNKNOWN"):
            first_p = self._pinch_buffer[0][1]
            last_p = self._pinch_buffer[-1][1]
            pinch_delta = last_p - first_p

            if abs(pinch_delta) >= self.pinch_spread_delta:
                # Hand should be relatively stable while zooming
                if palm_metrics.speed < (self.swipe_min_velocity * 0.8):
                    if pinch_delta > 0:
                        return MotionClassificationResult(
                            gesture="PINCH_OUT",
                            confidence=0.89,
                            description=f"Pinch Expanding (+{pinch_delta:.2f})",
                            metrics=palm_metrics
                        )
                    else:
                        return MotionClassificationResult(
                            gesture="PINCH_IN",
                            confidence=0.89,
                            description=f"Pinch Contracting ({pinch_delta:.2f})",
                            metrics=palm_metrics
                        )

        # ======================================================================
        # 5. DIRECTIONAL SWIPES (OPEN_PALM or Relaxed Hand)
        # ======================================================================
        if static_pose in ("OPEN_PALM", "UNKNOWN"):
            dx = palm_metrics.dx
            dy = palm_metrics.dy
            vx = palm_metrics.vx
            vy = palm_metrics.vy
            speed = palm_metrics.speed

            # Swipe Right / Left (Horizontal dominance: |dx| >> |dy|)
            if abs(dx) >= self.swipe_min_distance and abs(vx) >= self.swipe_min_velocity:
                if abs(dy) <= (abs(dx) * self.swipe_max_perp_ratio):
                    self.reset()
                    if dx > 0:
                        return MotionClassificationResult(
                            gesture="SWIPE_RIGHT",
                            confidence=0.93,
                            description=f"Swipe Right (dx: {dx:+.2f}, vx: {vx:+.2f})",
                            metrics=palm_metrics
                        )
                    else:
                        return MotionClassificationResult(
                            gesture="SWIPE_LEFT",
                            confidence=0.93,
                            description=f"Swipe Left (dx: {dx:+.2f}, vx: {vx:+.2f})",
                            metrics=palm_metrics
                        )

            # Swipe Up / Down (Vertical dominance: |dy| >> |dx|)
            if abs(dy) >= self.swipe_min_distance and abs(vy) >= self.swipe_min_velocity:
                if abs(dx) <= (abs(dy) * self.swipe_max_perp_ratio):
                    self.reset()
                    if dy < 0:  # Moving upward on screen
                        return MotionClassificationResult(
                            gesture="SWIPE_UP",
                            confidence=0.93,
                            description=f"Swipe Up (dy: {dy:+.2f}, vy: {vy:+.2f})",
                            metrics=palm_metrics
                        )
                    else:  # Moving downward on screen
                        return MotionClassificationResult(
                            gesture="SWIPE_DOWN",
                            confidence=0.93,
                            description=f"Swipe Down (dy: {dy:+.2f}, vy: {vy:+.2f})",
                            metrics=palm_metrics
                        )

        return MotionClassificationResult(
            gesture=None,
            confidence=0.0,
            description="No dynamic gesture",
            metrics=palm_metrics
        )
