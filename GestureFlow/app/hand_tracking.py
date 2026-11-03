"""
GestureFlow - Hand Tracking Module
Encapsulates MediaPipe Hands tracking, coordinate transformations,
bounding box calculations, and HUD annotation drawing.
"""

import math
from dataclasses import dataclass
from typing import List, Optional, Tuple
import cv2
import numpy as np

try:
    import mediapipe as mp
except ImportError:
    mp = None

from app.config import TrackingConfig


# Landmark Index Aliases for clarity
WRIST = 0
THUMB_CMC = 1
THUMB_MCP = 2
THUMB_IP = 3
THUMB_TIP = 4

INDEX_FINGER_MCP = 5
INDEX_FINGER_PIP = 6
INDEX_FINGER_DIP = 7
INDEX_FINGER_TIP = 8

MIDDLE_FINGER_MCP = 9
MIDDLE_FINGER_PIP = 10
MIDDLE_FINGER_DIP = 11
MIDDLE_FINGER_TIP = 12

RING_FINGER_MCP = 13
RING_FINGER_PIP = 14
RING_FINGER_DIP = 15
RING_FINGER_TIP = 16

PINKY_MCP = 17
PINKY_PIP = 18
PINKY_DIP = 19
PINKY_TIP = 20

# Standard hand skeleton connections
HAND_CONNECTIONS = (
    # Palm
    (WRIST, THUMB_CMC), (WRIST, INDEX_FINGER_MCP), (INDEX_FINGER_MCP, MIDDLE_FINGER_MCP),
    (MIDDLE_FINGER_MCP, RING_FINGER_MCP), (RING_FINGER_MCP, PINKY_MCP), (PINKY_MCP, WRIST),
    # Thumb
    (THUMB_CMC, THUMB_MCP), (THUMB_MCP, THUMB_IP), (THUMB_IP, THUMB_TIP),
    # Index
    (INDEX_FINGER_MCP, INDEX_FINGER_PIP), (INDEX_FINGER_PIP, INDEX_FINGER_DIP), (INDEX_FINGER_DIP, INDEX_FINGER_TIP),
    # Middle
    (MIDDLE_FINGER_MCP, MIDDLE_FINGER_PIP), (MIDDLE_FINGER_PIP, MIDDLE_FINGER_DIP), (MIDDLE_FINGER_DIP, MIDDLE_FINGER_TIP),
    # Ring
    (RING_FINGER_MCP, RING_FINGER_PIP), (RING_FINGER_PIP, RING_FINGER_DIP), (RING_FINGER_DIP, RING_FINGER_TIP),
    # Pinky
    (PINKY_MCP, PINKY_PIP), (PINKY_PIP, PINKY_DIP), (PINKY_DIP, PINKY_TIP),
)


@dataclass
class LandmarkPoint:
    """Normalized and pixel coordinates for a single landmark point."""
    idx: int
    x: float          # Normalized 0.0 - 1.0 (left to right)
    y: float          # Normalized 0.0 - 1.0 (top to bottom)
    z: float          # Relative depth
    px: int           # Pixel X coordinate
    py: int           # Pixel Y coordinate


@dataclass
class HandData:
    """Structured analysis for a detected hand in a frame."""
    landmarks: List[LandmarkPoint]
    handedness: str                        # "Left" or "Right"
    confidence: float
    bbox_pixel: Tuple[int, int, int, int]  # (min_x, min_y, max_x, max_y)
    bbox_norm: Tuple[float, float, float, float]
    palm_center_norm: Tuple[float, float]
    palm_center_pixel: Tuple[int, int]
    hand_scale: float                      # Normalized scale (distance from wrist to middle MCP)


class HandTracker:
    """
    MediaPipe Hands wrapper that produces structured hand geometric data
    and renders customizable computer vision overlays.
    """

    def __init__(self, config: Optional[TrackingConfig] = None):
        self.config = config or TrackingConfig()
        self.mp_hands = None
        self.hands = None
        self._init_mediapipe()

    def _init_mediapipe(self):
        if mp is None:
            return
        self.mp_hands = mp.solutions.hands
        self.hands = self.mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=self.config.max_num_hands,
            min_detection_confidence=self.config.min_detection_confidence,
            min_tracking_confidence=self.config.min_tracking_confidence,
            model_complexity=self.config.model_complexity
        )

    def process(self, frame: np.ndarray) -> List[HandData]:
        """
        Processes a BGR OpenCV frame and returns all detected hands.
        Handles missing MediaPipe or empty frames gracefully.
        """
        if self.hands is None or frame is None or frame.size == 0:
            return []

        h, w = frame.shape[:2]
        # MediaPipe expects RGB
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        rgb_frame.flags.writeable = False

        try:
            results = self.hands.process(rgb_frame)
        except Exception:
            return []

        if not results.multi_hand_landmarks:
            return []

        hands_list: List[HandData] = []
        for i, hand_landmarks in enumerate(results.multi_hand_landmarks):
            handedness_str = "Right"
            confidence = 0.90
            if results.multi_handedness and i < len(results.multi_handedness):
                handedness_str = results.multi_handedness[i].classification[0].label
                confidence = results.multi_handedness[i].classification[0].score

            landmarks: List[LandmarkPoint] = []
            xs_px, ys_px = [], []
            xs_norm, ys_norm = [], []

            for idx, lm in enumerate(hand_landmarks.landmark):
                px = int(min(max(lm.x * w, 0), w - 1))
                py = int(min(max(lm.y * h, 0), h - 1))
                landmarks.append(LandmarkPoint(
                    idx=idx,
                    x=lm.x,
                    y=lm.y,
                    z=lm.z,
                    px=px,
                    py=py
                ))
                xs_px.append(px)
                ys_px.append(py)
                xs_norm.append(lm.x)
                ys_norm.append(lm.y)

            # Bounding box
            pad = 12
            min_x_px = max(0, min(xs_px) - pad)
            min_y_px = max(0, min(ys_px) - pad)
            max_x_px = min(w - 1, max(xs_px) + pad)
            max_y_px = min(h - 1, max(ys_px) + pad)

            bbox_pixel = (min_x_px, min_y_px, max_x_px, max_y_px)
            bbox_norm = (min(xs_norm), min(ys_norm), max(xs_norm), max(ys_norm))

            # Palm center (average of wrist and knuckle bases)
            palm_indices = [WRIST, INDEX_FINGER_MCP, MIDDLE_FINGER_MCP, RING_FINGER_MCP, PINKY_MCP]
            cx_norm = sum(landmarks[idx].x for idx in palm_indices) / len(palm_indices)
            cy_norm = sum(landmarks[idx].y for idx in palm_indices) / len(palm_indices)
            cx_px = int(cx_norm * w)
            cy_px = int(cy_norm * h)

            # Hand scale (Euclidean distance between Wrist 0 and Middle MCP 9)
            scale = math.hypot(
                landmarks[MIDDLE_FINGER_MCP].x - landmarks[WRIST].x,
                landmarks[MIDDLE_FINGER_MCP].y - landmarks[WRIST].y
            )
            scale = max(scale, 0.05)  # Guard against division by zero

            hands_list.append(HandData(
                landmarks=landmarks,
                handedness=handedness_str,
                confidence=confidence,
                bbox_pixel=bbox_pixel,
                bbox_norm=bbox_norm,
                palm_center_norm=(cx_norm, cy_norm),
                palm_center_pixel=(cx_px, cy_px),
                hand_scale=scale
            ))

        return hands_list

    def draw_annotations(self, frame: np.ndarray, hands: List[HandData]) -> np.ndarray:
        """
        Draws sleek, modern HUD overlays on top of the frame.
        Includes glowing skeleton lines, joints, palm centers, and corner brackets.
        """
        if not hands or frame is None:
            return frame

        canvas = frame.copy()

        # Modern palette (BGR)
        COLOR_CONNECTION = (240, 160, 40)   # Vivid cyan-blue
        COLOR_JOINT = (255, 220, 80)        # Bright highlight cyan
        COLOR_PALM_CENTER = (80, 240, 120)  # Emerald green center
        COLOR_BBOX = (180, 120, 30)         # Sleek blue accent
        COLOR_TAG_BG = (25, 20, 15)         # Dark slate badge

        for hand in hands:
            # 1. Draw connections
            for p1_idx, p2_idx in HAND_CONNECTIONS:
                p1 = hand.landmarks[p1_idx]
                p2 = hand.landmarks[p2_idx]
                cv2.line(canvas, (p1.px, p1.py), (p2.px, p2.py), COLOR_CONNECTION, 2, cv2.LINE_AA)

            # 2. Draw landmark joints
            for lm in hand.landmarks:
                # Key fingertips get a slightly larger radius
                is_fingertip = lm.idx in (THUMB_TIP, INDEX_FINGER_TIP, MIDDLE_FINGER_TIP, RING_FINGER_TIP, PINKY_TIP)
                radius = 5 if is_fingertip else 3
                cv2.circle(canvas, (lm.px, lm.py), radius + 1, (20, 20, 20), -1, cv2.LINE_AA)
                cv2.circle(canvas, (lm.px, lm.py), radius, COLOR_JOINT, -1, cv2.LINE_AA)

            # 3. Palm center reticle
            cx, cy = hand.palm_center_pixel
            cv2.circle(canvas, (cx, cy), 6, COLOR_PALM_CENTER, -1, cv2.LINE_AA)
            cv2.circle(canvas, (cx, cy), 10, COLOR_PALM_CENTER, 1, cv2.LINE_AA)

            # 4. Corner bracket bounding box (sleek tech HUD)
            x1, y1, x2, y2 = hand.bbox_pixel
            bracket_len = min(20, (x2 - x1) // 4, (y2 - y1) // 4)

            # Top-left
            cv2.line(canvas, (x1, y1), (x1 + bracket_len, y1), COLOR_BBOX, 2, cv2.LINE_AA)
            cv2.line(canvas, (x1, y1), (x1, y1 + bracket_len), COLOR_BBOX, 2, cv2.LINE_AA)
            # Top-right
            cv2.line(canvas, (x2, y1), (x2 - bracket_len, y1), COLOR_BBOX, 2, cv2.LINE_AA)
            cv2.line(canvas, (x2, y1), (x2, y1 + bracket_len), COLOR_BBOX, 2, cv2.LINE_AA)
            # Bottom-left
            cv2.line(canvas, (x1, y2), (x1 + bracket_len, y2), COLOR_BBOX, 2, cv2.LINE_AA)
            cv2.line(canvas, (x1, y2), (x1, y2 - bracket_len), COLOR_BBOX, 2, cv2.LINE_AA)
            # Bottom-right
            cv2.line(canvas, (x2, y2), (x2 - bracket_len, y2), COLOR_BBOX, 2, cv2.LINE_AA)
            cv2.line(canvas, (x2, y2), (x2, y2 - bracket_len), COLOR_BBOX, 2, cv2.LINE_AA)

            # Handedness badge
            label = f"{hand.handedness} ({int(hand.confidence * 100)}%)"
            (lw, lh), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.42, 1)
            badge_y = max(y1 - 6, lh + 6)
            cv2.rectangle(
                canvas,
                (x1, badge_y - lh - 4),
                (x1 + lw + 10, badge_y + 4),
                COLOR_TAG_BG,
                -1
            )
            cv2.rectangle(
                canvas,
                (x1, badge_y - lh - 4),
                (x1 + lw + 10, badge_y + 4),
                COLOR_BBOX,
                1
            )
            cv2.putText(
                canvas,
                label,
                (x1 + 5, badge_y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.42,
                (240, 240, 240),
                1,
                cv2.LINE_AA
            )

        return canvas

    def close(self):
        """Release MediaPipe resources."""
        if self.hands is not None:
            try:
                self.hands.close()
            except Exception:
                pass
            self.hands = None
