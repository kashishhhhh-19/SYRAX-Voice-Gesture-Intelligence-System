"""
gesture/hand_tracker.py - Multi-Backend Hand Tracking Abstraction for SYRAX
Supports MediaPipe Tasks (HandLandmarker / GestureRecognizer with .task model),
legacy mp.solutions.hands, and adaptive OpenCV skin/contour fallback.
Applies centralized mirror correction, landmark smoothing, and hand lost grace period.
"""

import logging
import math
import os
import time
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import cv2
import numpy as np

logger = logging.getLogger("HandTracker")

# Standard MediaPipe 21 landmark topology
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

PALM_INDICES = [WRIST, INDEX_MCP, MIDDLE_MCP, RING_MCP, PINKY_MCP]

HAND_CONNECTIONS = (
    (WRIST, THUMB_CMC), (THUMB_CMC, THUMB_MCP), (THUMB_MCP, THUMB_IP), (THUMB_IP, THUMB_TIP),
    (WRIST, INDEX_MCP), (INDEX_MCP, INDEX_PIP), (INDEX_PIP, INDEX_DIP), (INDEX_DIP, INDEX_TIP),
    (INDEX_MCP, MIDDLE_MCP), (MIDDLE_MCP, MIDDLE_PIP), (MIDDLE_PIP, MIDDLE_DIP), (MIDDLE_DIP, MIDDLE_TIP),
    (MIDDLE_MCP, RING_MCP), (RING_MCP, RING_PIP), (RING_PIP, RING_DIP), (RING_DIP, RING_TIP),
    (RING_MCP, PINKY_MCP), (PINKY_MCP, PINKY_PIP), (PINKY_PIP, PINKY_DIP), (PINKY_DIP, PINKY_TIP),
    (PINKY_MCP, WRIST)
)


@dataclass
class LandmarkPoint:
    """Normalized (0.0 to 1.0) and pixel coordinates for a landmark."""
    idx: int
    x: float
    y: float
    z: float = 0.0
    px: int = 0
    py: int = 0


@dataclass
class HandResult:
    """Structured telemetry output for a single detected hand."""
    landmarks: List[LandmarkPoint]
    handedness: str                        # "Left", "Right", or "Unknown"
    score: float                           # Detection confidence [0.0 - 1.0]
    bbox_pixel: Tuple[int, int, int, int]  # (min_x, min_y, max_x, max_y)
    bbox_norm: Tuple[float, float, float, float]
    palm_center_norm: Tuple[float, float]
    palm_center_pixel: Tuple[int, int]
    hand_scale: float                      # Distance wrist -> middle MCP (scale normalizer)
    is_fallback: bool = False              # True if produced by OpenCV fallback


class HandTracker:
    """
    Unified Hand Tracking Engine with automatic backend selection:
    1. MediaPipe Tasks HandLandmarker / GestureRecognizer (.task file)
    2. MediaPipe Solutions Legacy (mp.solutions.hands)
    3. Adaptive OpenCV Fallback (color segmentation + convex hull)
    """

    def __init__(
        self,
        task_model_path: str = "models/hand_landmarker.task",
        gesture_model_path: str = "models/gesture_recognizer.task",
        max_num_hands: int = 1,
        min_detection_confidence: float = 0.65,
        min_tracking_confidence: float = 0.60,
        hand_lost_grace_period_ms: int = 200,
        smoothing_alpha: float = 0.65,
        preview_mirrored: bool = True
    ) -> None:
        self.task_model_path = task_model_path
        self.gesture_model_path = gesture_model_path
        self.max_num_hands = max_num_hands
        self.min_detection_confidence = min_detection_confidence
        self.min_tracking_confidence = min_tracking_confidence
        self.grace_period_sec = hand_lost_grace_period_ms / 1000.0
        self.smoothing_alpha = smoothing_alpha
        self.preview_mirrored = preview_mirrored

        self.active_backend: str = "Initializing..."
        self.fallback_reason: Optional[str] = None

        self._detector = None
        self._backend_kind: str = "none"  # "tasks_landmarker", "tasks_gesture", "legacy", "opencv"

        # Smoothing & Grace state
        self._prev_landmarks: Optional[List[Tuple[float, float, float]]] = None
        self._last_detected_time: float = 0.0
        self._last_result: Optional[HandResult] = None

        self._init_backend()

    def _init_backend(self) -> None:
        """Probe and initialize the strongest working hand tracking backend."""
        # 1. Try MediaPipe Tasks HandLandmarker with .task file
        if os.path.exists(self.task_model_path):
            try:
                import mediapipe as mp
                from mediapipe.tasks import python
                from mediapipe.tasks.python import vision

                base_options = python.BaseOptions(model_asset_path=self.task_model_path)
                options = vision.HandLandmarkerOptions(
                    base_options=base_options,
                    num_hands=self.max_num_hands,
                    min_hand_detection_confidence=self.min_detection_confidence,
                    min_tracking_confidence=self.min_tracking_confidence
                )
                self._detector = vision.HandLandmarker.create_from_options(options)
                self._backend_kind = "tasks_landmarker"
                self.active_backend = "MediaPipe HandLandmarker (Tasks)"
                logger.info(f"Initialized {self.active_backend} with model: {self.task_model_path}")
                return
            except Exception as task_err:
                logger.debug(f"Tasks HandLandmarker init failed: {task_err}")

        # 2. Try MediaPipe Tasks GestureRecognizer with .task file
        if os.path.exists(self.gesture_model_path):
            try:
                import mediapipe as mp
                from mediapipe.tasks import python
                from mediapipe.tasks.python import vision

                base_options = python.BaseOptions(model_asset_path=self.gesture_model_path)
                options = vision.GestureRecognizerOptions(
                    base_options=base_options,
                    num_hands=self.max_num_hands,
                    min_hand_detection_confidence=self.min_detection_confidence,
                    min_tracking_confidence=self.min_tracking_confidence
                )
                self._detector = vision.GestureRecognizer.create_from_options(options)
                self._backend_kind = "tasks_gesture"
                self.active_backend = "MediaPipe GestureRecognizer (Tasks)"
                logger.info(f"Initialized {self.active_backend} with model: {self.gesture_model_path}")
                return
            except Exception as gest_err:
                logger.debug(f"Tasks GestureRecognizer init failed: {gest_err}")

        # 3. Try legacy mp.solutions.hands
        try:
            import mediapipe as mp
            if hasattr(mp, "solutions") and hasattr(mp.solutions, "hands"):
                self._detector = mp.solutions.hands.Hands(
                    static_image_mode=False,
                    max_num_hands=self.max_num_hands,
                    min_detection_confidence=self.min_detection_confidence,
                    min_tracking_confidence=self.min_tracking_confidence
                )
                self._backend_kind = "legacy"
                self.active_backend = "MediaPipe Hands (legacy)"
                logger.info(f"Initialized {self.active_backend}")
                return
        except Exception as leg_err:
            logger.debug(f"Legacy mp.solutions init failed: {leg_err}")

        # 4. Fallback: Adaptive OpenCV
        self._backend_kind = "opencv"
        self.active_backend = "OpenCV fallback (reduced accuracy)"
        self.fallback_reason = "MediaPipe tasks model or solutions unavailable on this Python environment."
        logger.info(f"Using {self.active_backend}. Reason: {self.fallback_reason}")

    def process(self, frame: np.ndarray) -> List[HandResult]:
        """
        Process a BGR webcam frame and return list of detected hands.
        Handles mirror correction, coordinate normalization, smoothing, and grace periods.
        """
        now = time.time()
        if frame is None or frame.size == 0:
            return self._handle_hand_lost(now)

        h, w = frame.shape[:2]

        results: List[HandResult] = []
        if self._backend_kind == "tasks_landmarker":
            results = self._process_tasks_landmarker(frame, w, h)
        elif self._backend_kind == "tasks_gesture":
            results = self._process_tasks_gesture(frame, w, h)
        elif self._backend_kind == "legacy":
            results = self._process_legacy(frame, w, h)
        else:
            results = self._process_opencv(frame, w, h)

        if results:
            self._last_detected_time = now
            self._last_result = results[0]
            # Smooth primary hand landmarks
            smoothed_res = self._apply_smoothing(results[0], w, h)
            return [smoothed_res]

        return self._handle_hand_lost(now)

    def _handle_hand_lost(self, now: float) -> List[HandResult]:
        """Return cached result within grace period, or clear tracking on loss."""
        if self._last_result is not None and (now - self._last_detected_time) < self.grace_period_sec:
            return [self._last_result]
        self._prev_landmarks = None
        self._last_result = None
        return []

    def _correct_handedness(self, raw_label: str) -> str:
        """
        Correct handedness for mirrored preview.
        When viewing a mirrored selfie camera, moving the physical right hand appears on the right
        side of the screen, so raw classification ('Left') is inverted.
        """
        if not self.preview_mirrored:
            return raw_label
        if raw_label.lower() == "left":
            return "Right"
        elif raw_label.lower() == "right":
            return "Left"
        return "Unknown"

    def _build_hand_result(
        self,
        raw_coords: List[Tuple[float, float, float]],
        handedness: str,
        score: float,
        w: int,
        h: int,
        is_fallback: bool = False
    ) -> HandResult:
        """Construct structured HandResult from 21 normalized (x, y, z) coordinates."""
        landmarks: List[LandmarkPoint] = []
        xs_norm, ys_norm = [], []
        xs_px, ys_px = [], []

        for idx, (x, y, z) in enumerate(raw_coords):
            # Clamp normalized coords to [0.0, 1.0]
            cx_n = min(max(x, 0.0), 1.0)
            cy_n = min(max(y, 0.0), 1.0)
            px = int(cx_n * w)
            py = int(cy_n * h)

            landmarks.append(LandmarkPoint(idx=idx, x=cx_n, y=cy_n, z=z, px=px, py=py))
            xs_norm.append(cx_n)
            ys_norm.append(cy_n)
            xs_px.append(px)
            ys_px.append(py)

        # Bounding box with padding
        pad_px = 12
        min_x_px = max(0, min(xs_px) - pad_px)
        min_y_px = max(0, min(ys_px) - pad_px)
        max_x_px = min(w - 1, max(xs_px) + pad_px)
        max_y_px = min(h - 1, max(ys_px) + pad_px)

        bbox_pixel = (min_x_px, min_y_px, max_x_px, max_y_px)
        bbox_norm = (min(xs_norm), min(ys_norm), max(xs_norm), max(ys_norm))

        # Palm center: average of WRIST and 4 MCP knuckle bases
        cx_norm = sum(landmarks[i].x for i in PALM_INDICES) / len(PALM_INDICES)
        cy_norm = sum(landmarks[i].y for i in PALM_INDICES) / len(PALM_INDICES)
        cx_px = int(cx_norm * w)
        cy_px = int(cy_norm * h)

        # Hand scale: Euclidean distance between Wrist (0) and Middle MCP (9)
        w_lm = landmarks[WRIST]
        m_lm = landmarks[MIDDLE_MCP]
        hand_scale = math.hypot(m_lm.x - w_lm.x, m_lm.y - w_lm.y)
        hand_scale = max(0.05, hand_scale)

        return HandResult(
            landmarks=landmarks,
            handedness=handedness,
            score=score,
            bbox_pixel=bbox_pixel,
            bbox_norm=bbox_norm,
            palm_center_norm=(cx_norm, cy_norm),
            palm_center_pixel=(cx_px, cy_px),
            hand_scale=hand_scale,
            is_fallback=is_fallback
        )

    def _apply_smoothing(self, res: HandResult, w: int, h: int) -> HandResult:
        """Exponential Moving Average (EMA) smoothing over 21 landmark points."""
        current_coords = [(lm.x, lm.y, lm.z) for lm in res.landmarks]

        if self._prev_landmarks is None or len(self._prev_landmarks) != 21:
            self._prev_landmarks = current_coords
            return res

        alpha = self.smoothing_alpha
        smoothed_coords: List[Tuple[float, float, float]] = []
        for curr, prev in zip(current_coords, self._prev_landmarks):
            sx = alpha * curr[0] + (1.0 - alpha) * prev[0]
            sy = alpha * curr[1] + (1.0 - alpha) * prev[1]
            sz = alpha * curr[2] + (1.0 - alpha) * prev[2]
            smoothed_coords.append((sx, sy, sz))

        self._prev_landmarks = smoothed_coords
        return self._build_hand_result(
            smoothed_coords,
            res.handedness,
            res.score,
            w,
            h,
            is_fallback=res.is_fallback
        )

    def _process_tasks_landmarker(self, frame: np.ndarray, w: int, h: int) -> List[HandResult]:
        """Inference via MediaPipe Tasks HandLandmarker."""
        import mediapipe as mp
        try:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            detection = self._detector.detect(mp_image)

            if not detection.hand_landmarks:
                return []

            results: List[HandResult] = []
            for i, hand_lms in enumerate(detection.hand_landmarks):
                raw_coords = [(lm.x, lm.y, lm.z) for lm in hand_lms]
                raw_label = "Right"
                score = 0.90
                if detection.handedness and i < len(detection.handedness):
                    raw_label = detection.handedness[i][0].category_name
                    score = detection.handedness[i][0].score

                corrected_handedness = self._correct_handedness(raw_label)
                results.append(self._build_hand_result(raw_coords, corrected_handedness, score, w, h))
                break  # Primary hand only

            return results
        except Exception as exc:
            logger.debug(f"Tasks HandLandmarker inference error: {exc}")
            return []

    def _process_tasks_gesture(self, frame: np.ndarray, w: int, h: int) -> List[HandResult]:
        """Inference via MediaPipe Tasks GestureRecognizer."""
        import mediapipe as mp
        try:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            detection = self._detector.recognize(mp_image)

            if not detection.hand_landmarks:
                return []

            results: List[HandResult] = []
            for i, hand_lms in enumerate(detection.hand_landmarks):
                raw_coords = [(lm.x, lm.y, lm.z) for lm in hand_lms]
                raw_label = "Right"
                score = 0.90
                if detection.handedness and i < len(detection.handedness):
                    raw_label = detection.handedness[i][0].category_name
                    score = detection.handedness[i][0].score

                corrected_handedness = self._correct_handedness(raw_label)
                results.append(self._build_hand_result(raw_coords, corrected_handedness, score, w, h))
                break

            return results
        except Exception as exc:
            logger.debug(f"Tasks GestureRecognizer inference error: {exc}")
            return []

    def _process_legacy(self, frame: np.ndarray, w: int, h: int) -> List[HandResult]:
        """Inference via legacy mp.solutions.hands."""
        try:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            detection = self._detector.process(rgb)
            if not detection.multi_hand_landmarks:
                return []

            results: List[HandResult] = []
            for i, hand_lms in enumerate(detection.multi_hand_landmarks):
                raw_coords = [(lm.x, lm.y, lm.z) for lm in hand_lms.landmark]
                raw_label = "Right"
                score = 0.90
                if detection.multi_handedness and i < len(detection.multi_handedness):
                    raw_label = detection.multi_handedness[i].classification[0].label
                    score = detection.multi_handedness[i].classification[0].score

                corrected_handedness = self._correct_handedness(raw_label)
                results.append(self._build_hand_result(raw_coords, corrected_handedness, score, w, h))
                break

            return results
        except Exception as exc:
            logger.debug(f"Legacy mp inference error: {exc}")
            return []

    def _process_opencv(self, frame: np.ndarray, w: int, h: int) -> List[HandResult]:
        """Adaptive OpenCV skin segmentation and contour fallback."""
        try:
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            lower_skin = np.array([0, 30, 60], dtype=np.uint8)
            upper_skin = np.array([20, 255, 255], dtype=np.uint8)
            mask = cv2.inRange(hsv, lower_skin, upper_skin)

            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
            mask = cv2.dilate(mask, kernel, iterations=2)
            mask = cv2.GaussianBlur(mask, (5, 5), 100)

            contours, _ = cv2.findContours(mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
            if not contours:
                return []

            max_contour = max(contours, key=cv2.contourArea)
            area = cv2.contourArea(max_contour)
            if area < 6000:
                return []

            M = cv2.moments(max_contour)
            if M["m00"] == 0:
                return []

            cx = int(M["m10"] / M["m00"])
            cy = int(M["m01"] / M["m00"])
            norm_cx = cx / w
            norm_cy = cy / h

            # Hull points
            hull = cv2.convexHull(max_contour, returnPoints=True)
            top_pts = sorted([p[0] for p in hull], key=lambda pt: pt[1])[:5]

            # Synthesize 21 landmarks
            wrist_x = norm_cx
            wrist_y = min(1.0, norm_cy + 0.22)
            coords: List[Tuple[float, float, float]] = [(wrist_x, wrist_y, 0.0)]  # 0: Wrist

            # Interpolate fingers
            for i in range(1, 5):
                # Thumb
                coords.append((norm_cx - 0.08 * (i / 4), norm_cy - 0.05 * (i / 4), 0.0))
            for f_idx in range(4):
                tip_pt = top_pts[min(f_idx, len(top_pts) - 1)]
                tip_norm_x = tip_pt[0] / w
                tip_norm_y = tip_pt[1] / h
                for j in range(1, 5):
                    # MCP, PIP, DIP, TIP
                    ratio = j / 4.0
                    ix = norm_cx + (tip_norm_x - norm_cx) * ratio
                    iy = norm_cy + (tip_norm_y - norm_cy) * ratio
                    coords.append((ix, iy, 0.0))

            while len(coords) < 21:
                coords.append((norm_cx, norm_cy, 0.0))
            coords = coords[:21]

            return [self._build_hand_result(
                coords,
                handedness="Unknown",
                score=0.60,
                w=w,
                h=h,
                is_fallback=True
            )]
        except Exception as cv_err:
            logger.debug(f"OpenCV fallback tracker error: {cv_err}")
            return []
