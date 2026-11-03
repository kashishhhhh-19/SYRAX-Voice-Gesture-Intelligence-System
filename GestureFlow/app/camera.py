"""
GestureFlow - Camera Capture Module
Manages OpenCV webcam acquisition, device fallback, frame mirroring,
FPS calculation, error detection, and graceful resource release.
"""

import time
import cv2
import numpy as np
from enum import Enum
from typing import Optional, Tuple
from app.config import CameraConfig


class CameraStatus(Enum):
    DISCONNECTED = "Disconnected"
    CONNECTING = "Connecting..."
    ACTIVE = "Active"
    ERROR = "Camera Error"
    NO_DEVICE = "No Camera Detected"


class CameraManager:
    """
    Robust camera acquisition wrapper for OpenCV.
    Provides device probing, auto-reconnect, FPS monitoring, and mirrored frames.
    """

    def __init__(self, config: Optional[CameraConfig] = None):
        self.config = config or CameraConfig()
        self.cap: Optional[cv2.VideoCapture] = None
        self.status: CameraStatus = CameraStatus.DISCONNECTED
        self.error_message: str = ""
        self.active_index: int = self.config.camera_index

        # Telemetry & performance metrics
        self._fps: float = 0.0
        self._frame_count: int = 0
        self._fps_timer: float = time.time()
        self._fps_frame_counter: int = 0
        self._last_frame_time: float = 0.0
        self._capture_latency_ms: float = 0.0

    @property
    def is_running(self) -> bool:
        return self.status == CameraStatus.ACTIVE and self.cap is not None and self.cap.isOpened()

    @property
    def current_fps(self) -> float:
        return self._fps

    @property
    def latency_ms(self) -> float:
        return self._capture_latency_ms

    def start(self, camera_index: Optional[int] = None) -> bool:
        """
        Attempts to open the specified camera or probes configured fallbacks.
        Uses cv2.CAP_DSHOW on Windows for fast startup and low latency.
        """
        self.status = CameraStatus.CONNECTING
        self.error_message = ""

        indices_to_try = []
        if camera_index is not None:
            indices_to_try.append(camera_index)
        else:
            indices_to_try.append(self.config.camera_index)
            for idx in self.config.fallback_indices:
                if idx not in indices_to_try:
                    indices_to_try.append(idx)

        for idx in indices_to_try:
            try:
                # DirectShow (CAP_DSHOW) ensures fast initialization on Windows
                cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
                if not cap.isOpened():
                    # Fallback to default API if DSHOW failed
                    cap.release()
                    cap = cv2.VideoCapture(idx)

                if cap.isOpened():
                    # Set requested resolution
                    cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.config.frame_width)
                    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.config.frame_height)
                    cap.set(cv2.CAP_PROP_FPS, self.config.target_fps)

                    # Test read a frame to confirm stream is working
                    ret, test_frame = cap.read()
                    if ret and test_frame is not None and test_frame.size > 0:
                        self.cap = cap
                        self.active_index = idx
                        self.status = CameraStatus.ACTIVE
                        self._fps_timer = time.time()
                        self._fps_frame_counter = 0
                        return True
                    else:
                        cap.release()
            except Exception as e:
                self.error_message = f"Error opening camera index {idx}: {str(e)}"

        self.status = CameraStatus.NO_DEVICE
        self.error_message = (
            f"Could not connect to any camera (probed indices: {indices_to_try}). "
            "Please ensure your webcam is connected and not in use by another app."
        )
        return False

    def read_frame(self) -> Tuple[bool, Optional[np.ndarray]]:
        """
        Reads and returns a frame from the active webcam.
        Applies horizontal mirroring if configured.
        Calculates instantaneous capture latency and running FPS.
        """
        if not self.is_running or self.cap is None:
            return False, None

        t0 = time.perf_counter()
        ret, frame = self.cap.read()
        self._capture_latency_ms = (time.perf_counter() - t0) * 1000.0

        if not ret or frame is None or frame.size == 0:
            self.status = CameraStatus.ERROR
            self.error_message = "Webcam stream interrupted or frame empty."
            return False, None

        # Horizontal flip for intuitive mirror preview
        if self.config.mirror_frame:
            frame = cv2.flip(frame, 1)

        # Update FPS counters
        self._frame_count += 1
        self._fps_frame_counter += 1
        now = time.time()
        dt = now - self._fps_timer
        if dt >= 0.5:
            self._fps = round(self._fps_frame_counter / dt, 1)
            self._fps_timer = now
            self._fps_frame_counter = 0

        self._last_frame_time = now
        return True, frame

    def stop(self) -> None:
        """Safely stops acquisition and releases hardware resources."""
        if self.cap is not None:
            try:
                self.cap.release()
            except Exception:
                pass
            self.cap = None

        self.status = CameraStatus.DISCONNECTED
        self._fps = 0.0

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
