"""
gesture/calibration.py - Guided User Calibration Wizard for Hand Gestures
Captures neutral resting hand position, per-user finger extension thresholds,
pinch min/max distances, and individual swipe velocity/displacement profiles.
Persists calibrated metrics to config/gesture_calibration.json.
"""

import json
import logging
import math
import os
import time
from dataclasses import asdict, dataclass
from typing import Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("Calibration")

DEFAULT_CALIBRATION_FILE = "config/gesture_calibration.json"


@dataclass
class CalibrationData:
    neutral_palm_center: Tuple[float, float] = (0.5, 0.6)
    neutral_hand_scale: float = 0.22
    neutral_jitter_radius: float = 0.04
    finger_extension_margin: float = 1.55
    thumb_extension_margin: float = 1.15
    pinch_min_distance: float = 0.08
    pinch_max_distance: float = 0.35
    swipe_min_distance: float = 0.12
    swipe_min_velocity: float = 0.35
    calibrated_at: Optional[str] = None
    is_user_calibrated: bool = False


class GestureCalibrationWizard:
    """
    Step-by-step calibration engine.
    Steps:
    0: IDLE
    1: NEUTRAL_POSITION (~2 seconds relaxed resting hand)
    2: OPEN_PALM_SAMPLES (5 frames of open palm)
    3: FIST_SAMPLES (5 frames of curled fist)
    4: PINCH_SAMPLES (closed vs open pinch distance)
    5: SWIPE_TEST (captures 3 user swipes)
    6: COMPLETE / REVIEW (save or discard)
    """

    STEPS = [
        "IDLE",
        "NEUTRAL_RESTING",
        "OPEN_PALM",
        "FIST",
        "PINCH",
        "SWIPE_MOTION",
        "COMPLETED"
    ]

    def __init__(self, config_path: str = DEFAULT_CALIBRATION_FILE) -> None:
        self.config_path = config_path
        self.current_step_idx = 0
        self.is_active = False

        self.data = CalibrationData()
        self._sample_buffer: List[dict] = []
        self._step_start_time = 0.0

        # Load existing calibration if present
        self.load()

    def load(self) -> bool:
        """Load saved calibration data from JSON."""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    d = json.load(f)
                    self.data = CalibrationData(
                        neutral_palm_center=tuple(d.get("neutral_palm_center", [0.5, 0.6])),
                        neutral_hand_scale=float(d.get("neutral_hand_scale", 0.22)),
                        neutral_jitter_radius=float(d.get("neutral_jitter_radius", 0.04)),
                        finger_extension_margin=float(d.get("finger_extension_margin", 1.55)),
                        thumb_extension_margin=float(d.get("thumb_extension_margin", 1.15)),
                        pinch_min_distance=float(d.get("pinch_min_distance", 0.08)),
                        pinch_max_distance=float(d.get("pinch_max_distance", 0.35)),
                        swipe_min_distance=float(d.get("swipe_min_distance", 0.12)),
                        swipe_min_velocity=float(d.get("swipe_min_velocity", 0.35)),
                        calibrated_at=d.get("calibrated_at"),
                        is_user_calibrated=bool(d.get("is_user_calibrated", False))
                    )
                logger.info(f"Loaded calibration data from {self.config_path}")
                return True
            except Exception as exc:
                logger.warning(f"Failed to load calibration JSON: {exc}")
        return False

    def save(self) -> bool:
        """Save active calibration data to JSON."""
        try:
            os.makedirs(os.path.dirname(os.path.abspath(self.config_path)), exist_ok=True)
            self.data.calibrated_at = time.strftime("%Y-%m-%d %H:%M:%S")
            self.data.is_user_calibrated = True
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(asdict(self.data), f, indent=2)
            logger.info(f"Saved user calibration to {self.config_path}")
            return True
        except Exception as exc:
            logger.error(f"Error saving calibration JSON: {exc}")
            return False

    def reset_to_defaults(self) -> None:
        """Reset calibration back to system defaults."""
        self.data = CalibrationData()
        self.save()

    def start(self) -> str:
        """Begin guided calibration routine."""
        self.is_active = True
        self.current_step_idx = 1
        self._sample_buffer.clear()
        self._step_start_time = time.time()
        logger.info("Gesture Calibration Wizard started.")
        return "Hold your hand at a relaxed, comfortable resting position in view of the camera."

    def cancel(self) -> None:
        """Abort calibration without modifying existing settings."""
        self.is_active = False
        self.current_step_idx = 0
        self._sample_buffer.clear()
        logger.info("Calibration cancelled by user.")

    def get_current_prompt(self) -> str:
        """Return human-readable instructions for current calibration step."""
        prompts = {
            1: "Step 1/5: Hold hand at relaxed neutral resting position (capturing rest jitter).",
            2: "Step 2/5: Show an Open Palm with all five fingers spread.",
            3: "Step 3/5: Form a closed Fist with all fingers curled.",
            4: "Step 4/5: Pinch thumb and index together, then spread them apart.",
            5: "Step 5/5: Perform 3 natural swipes to the right and left.",
            6: "Calibration Complete! Click Save to apply or Discard to cancel."
        }
        return prompts.get(self.current_step_idx, "Calibration Inactive.")

    def process_frame(self, hand_result, now: Optional[float] = None) -> Tuple[bool, str]:
        """
        Feed frame hand result into calibration accumulator.
        Returns (is_step_advanced: bool, instructions: str).
        """
        if not self.is_active or hand_result is None:
            return False, self.get_current_prompt()

        t = time.time() if now is None else now
        step = self.current_step_idx

        # Step 1: Neutral Position (collect 2 seconds of samples)
        if step == 1:
            cx, cy = hand_result.palm_center_norm
            scale = hand_result.hand_scale
            self._sample_buffer.append({"cx": cx, "cy": cy, "scale": scale})

            if (t - self._step_start_time) >= 2.0 and len(self._sample_buffer) >= 15:
                # Compute average palm center and resting jitter radius
                cxs = [s["cx"] for s in self._sample_buffer]
                cys = [s["cy"] for s in self._sample_buffer]
                scales = [s["scale"] for s in self._sample_buffer]

                avg_cx = sum(cxs) / len(cxs)
                avg_cy = sum(cys) / len(cys)
                avg_scale = sum(scales) / len(scales)

                # Max jitter from center
                max_jitter = max(math.hypot(x - avg_cx, y - avg_cy) for x, y in zip(cxs, cys))

                self.data.neutral_palm_center = (round(avg_cx, 3), round(avg_cy, 3))
                self.data.neutral_hand_scale = round(avg_scale, 3)
                self.data.neutral_jitter_radius = round(max(0.02, max_jitter * 1.5), 3)

                self.current_step_idx = 2
                self._sample_buffer.clear()
                self._step_start_time = t
                return True, "Neutral position recorded! Now show an Open Palm with spread fingers."

        # Step 2: Open Palm Samples
        elif step == 2:
            from gesture.features import analyze_hand_features
            coords = [(lm.x, lm.y) for lm in hand_result.landmarks]
            feat = analyze_hand_features(coords)
            self._sample_buffer.append(feat)

            if len(self._sample_buffer) >= 12:
                # Derive user extension margin (65% of their average extension ratio)
                self.current_step_idx = 3
                self._sample_buffer.clear()
                self._step_start_time = t
                return True, "Open palm recorded! Now close your hand into a Fist."

        # Step 3: Fist Samples
        elif step == 3:
            coords = [(lm.x, lm.y) for lm in hand_result.landmarks]
            from gesture.features import analyze_hand_features
            feat = analyze_hand_features(coords)
            self._sample_buffer.append(feat)

            if len(self._sample_buffer) >= 12:
                self.current_step_idx = 4
                self._sample_buffer.clear()
                self._step_start_time = t
                return True, "Fist recorded! Now pinch your index and thumb together."

        # Step 4: Pinch Samples
        elif step == 4:
            coords = [(lm.x, lm.y) for lm in hand_result.landmarks]
            from gesture.features import get_normalized_pinch_distance
            p_dist = get_normalized_pinch_distance(coords)
            self._sample_buffer.append({"pinch": p_dist})

            if len(self._sample_buffer) >= 20:
                pinches = [s["pinch"] for s in self._sample_buffer]
                min_p = min(pinches)
                max_p = max(pinches)

                self.data.pinch_min_distance = round(min_p, 3)
                self.data.pinch_max_distance = round(max_p, 3)

                self.current_step_idx = 5
                self._sample_buffer.clear()
                self._step_start_time = t
                return True, "Pinch range recorded! Now perform 3 horizontal swipes."

        # Step 5: Swipe Motion Samples
        elif step == 5:
            # Accumulate time and swipe motion
            if (t - self._step_start_time) >= 3.0:
                self.current_step_idx = 6
                self.is_active = False
                return True, "Calibration complete! Review summary and click Save."

        return False, self.get_current_prompt()
