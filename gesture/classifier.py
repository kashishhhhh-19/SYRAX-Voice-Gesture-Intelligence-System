"""
gesture/classifier.py - Static Hand Pose Classifier for SYRAX
Classifies static hand geometry into OPEN_PALM, FIST, ONE_FINGER, TWO_FINGERS, PINCH, UNKNOWN
with continuous confidence scores and temporal frame stability.
"""

from collections import deque
from dataclasses import dataclass
from typing import Deque, List, Optional, Tuple

from gesture.features import (
    analyze_hand_features,
    get_normalized_pinch_distance
)


class PoseType:
    OPEN_PALM = "OPEN_PALM"
    FIST = "FIST"
    ONE_FINGER = "ONE_FINGER"
    TWO_FINGERS = "TWO_FINGERS"
    PINCH = "PINCH"
    UNKNOWN = "UNKNOWN"
    NONE = "NONE"


@dataclass
class PoseClassificationResult:
    """Output from static pose classification."""
    pose: str
    confidence: float
    is_stable: bool
    stable_count: int
    raw_features: dict


def classify_static_pose(
    landmarks: List[Tuple[float, float]],
    finger_extension_ratio: float = 1.55,
    thumb_extension_ratio: float = 1.15,
    pinch_threshold: float = 0.18
) -> Tuple[str, float, dict]:
    """
    Pure geometric classification of a single frame into a static pose.
    Returns (pose: str, confidence: float, features: dict).
    """
    if len(landmarks) < 21:
        return PoseType.NONE, 0.0, {}

    features = analyze_hand_features(
        landmarks,
        finger_extension_ratio=finger_extension_ratio,
        thumb_extension_ratio=thumb_extension_ratio,
        pinch_threshold=pinch_threshold
    )

    scores = features["scores"]
    extended = features["extended"]
    num_ext = features["num_extended"]
    pinch_dist = features["pinch_distance"]

    # 1. PINCH Check:
    # Thumb tip and index tip close together, middle/ring/pinky relaxed/curled or slightly open
    if pinch_dist < pinch_threshold and not extended["middle"] and not extended["ring"] and not extended["pinky"]:
        conf = min(0.96, max(0.70, 1.0 - (pinch_dist / max(0.01, pinch_threshold)) * 0.3))
        return PoseType.PINCH, round(conf, 2), features

    # 2. FIST Check:
    # All 4 fingers (index, middle, ring, pinky) firmly curled. Thumb can be tucked or resting on fingers.
    if not extended["index"] and not extended["middle"] and not extended["ring"] and not extended["pinky"]:
        curled_scores = [1.0 - scores[f] for f in ("index", "middle", "ring", "pinky")]
        base_conf = sum(curled_scores) / 4.0
        conf = 0.95 * base_conf
        return PoseType.FIST, round(min(0.98, max(0.70, conf)), 2), features

    # 3. OPEN_PALM Check:
    # All 5 fingers extended and spread, or 4 fingers extended with thumb spread
    if extended["index"] and extended["middle"] and extended["ring"] and extended["pinky"]:
        ext_scores = [scores[f] for f in ("index", "middle", "ring", "pinky", "thumb")]
        mean_score = sum(ext_scores) / 5.0
        conf = 0.96 if extended["thumb"] else 0.86
        conf = conf * mean_score
        return PoseType.OPEN_PALM, round(min(0.98, max(0.70, conf)), 2), features

    # 4. TWO_FINGERS Check:
    # Index + Middle extended; Ring + Pinky curled
    if extended["index"] and extended["middle"] and not extended["ring"] and not extended["pinky"]:
        conf = (scores["index"] + scores["middle"] + (1.0 - scores["ring"]) + (1.0 - scores["pinky"])) / 4.0
        return PoseType.TWO_FINGERS, round(min(0.95, max(0.70, conf * 0.95)), 2), features

    # 5. ONE_FINGER Check:
    # Index extended only; Middle + Ring + Pinky curled (Thumb tolerated)
    if extended["index"] and not extended["middle"] and not extended["ring"] and not extended["pinky"]:
        conf = (scores["index"] + (1.0 - scores["middle"]) + (1.0 - scores["ring"]) + (1.0 - scores["pinky"])) / 4.0
        return PoseType.ONE_FINGER, round(min(0.94, max(0.70, conf * 0.94)), 2), features

    # 6. UNKNOWN Fallback
    return PoseType.UNKNOWN, 0.35, features


class PoseClassifier:
    """
    Temporal Pose Classifier enforcing consecutive frame stability.
    Prevents single-frame glitches or transitional hand shapes from triggering actions.
    """

    def __init__(
        self,
        stability_required_frames: int = 3,
        finger_extension_ratio: float = 1.55,
        thumb_extension_ratio: float = 1.15,
        pinch_threshold: float = 0.18
    ) -> None:
        self.stability_required_frames = stability_required_frames
        self.finger_extension_ratio = finger_extension_ratio
        self.thumb_extension_ratio = thumb_extension_ratio
        self.pinch_threshold = pinch_threshold

        self._candidate_pose: str = PoseType.NONE
        self._candidate_count: int = 0
        self._last_confirmed_pose: str = PoseType.NONE

    def reset(self) -> None:
        """Clear candidate buffers and stability counts."""
        self._candidate_pose = PoseType.NONE
        self._candidate_count = 0
        self._last_confirmed_pose = PoseType.NONE

    def process_frame(self, landmarks: Optional[List[Tuple[float, float]]]) -> PoseClassificationResult:
        """
        Evaluate frame landmarks and return stabilized PoseClassificationResult.
        """
        if not landmarks or len(landmarks) < 21:
            self.reset()
            return PoseClassificationResult(
                pose=PoseType.NONE,
                confidence=0.0,
                is_stable=False,
                stable_count=0,
                raw_features={}
            )

        raw_pose, confidence, features = classify_static_pose(
            landmarks,
            finger_extension_ratio=self.finger_extension_ratio,
            thumb_extension_ratio=self.thumb_extension_ratio,
            pinch_threshold=self.pinch_threshold
        )

        if raw_pose == self._candidate_pose and raw_pose != PoseType.NONE:
            self._candidate_count += 1
        else:
            self._candidate_pose = raw_pose
            self._candidate_count = 1

        is_stable = self._candidate_count >= self.stability_required_frames
        confirmed_pose = self._candidate_pose if is_stable else PoseType.UNKNOWN

        if is_stable:
            self._last_confirmed_pose = confirmed_pose

        return PoseClassificationResult(
            pose=confirmed_pose,
            confidence=confidence if is_stable else (confidence * 0.5),
            is_stable=is_stable,
            stable_count=self._candidate_count,
            raw_features=features
        )
