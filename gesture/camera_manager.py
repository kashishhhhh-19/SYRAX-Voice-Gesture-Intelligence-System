"""
gesture/camera_manager.py - Single Owner of Webcam Hardware for SYRAX
Manages cv2.VideoCapture with DirectShow/MSMF backends, automatic device enumeration,
low-light detection, CLAHE brightness enhancement, thread-safe access, read failure detection,
and automatic reconnect with backoff.
"""

import enum
import logging
import subprocess
import threading
import time
from typing import Optional, Tuple

import cv2
import numpy as np

logger = logging.getLogger("CameraManager")


class CameraState(enum.Enum):
    STOPPED = "STOPPED"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    ERROR = "ERROR"
    DISCONNECTED = "DISCONNECTED"
    RECOVERING = "RECOVERING"


class CameraManager:
    """
    Thread-safe webcam manager.
    Single owner of cv2.VideoCapture with robust lifecycle and fault tolerance.
    """

    def __init__(
        self,
        camera_index: int = 0,
        width: int = 640,
        height: int = 480,
        fps: int = 30,
        low_light_threshold: float = 45.0,
        clahe_enhancement: bool = True,
        max_read_failures: int = 10,
        reconnect_interval: float = 2.0,
    ) -> None:
        self.camera_index = camera_index
        self.target_width = width
        self.target_height = height
        self.target_fps = fps
        self.low_light_threshold = low_light_threshold
        self.clahe_enhancement = clahe_enhancement
        self.max_read_failures = max_read_failures
        self.reconnect_interval = reconnect_interval

        self._cap: Optional[cv2.VideoCapture] = None
        self._state = CameraState.STOPPED
        self._state_lock = threading.RLock()
        self._device_name: str = self._discover_device_name(camera_index)
        self._consecutive_failures = 0
        self._is_low_light = False
        self._last_reconnect_attempt = 0.0

        # Contrast Limited Adaptive Histogram Equalizer for low light
        self._clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))

    @property
    def state(self) -> CameraState:
        with self._state_lock:
            return self._state

    @property
    def device_name(self) -> str:
        return self._device_name

    @property
    def is_low_light(self) -> bool:
        return self._is_low_light

    def _discover_device_name(self, index: int) -> str:
        """Discover friendly webcam name via Windows PowerShell PnP device query."""
        try:
            cmd = [
                "powershell",
                "-NoProfile",
                "-Command",
                "Get-PnpDevice -Class Camera -Status OK | Select-Object -ExpandProperty FriendlyName"
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=3.0)
            if res.returncode == 0 and res.stdout.strip():
                lines = [line.strip() for line in res.stdout.splitlines() if line.strip()]
                if 0 <= index < len(lines):
                    return lines[index]
                elif lines:
                    return lines[0]
        except Exception as exc:
            logger.debug(f"PnP camera name lookup failed: {exc}")

        return f"Webcam (Index {index})"

    def start(self) -> bool:
        """
        Open webcam hardware and enter RUNNING state.
        Thread-safe; returns True on success.
        """
        with self._state_lock:
            if self._state == CameraState.RUNNING and self._cap is not None and self._cap.isOpened():
                return True

            self._state = CameraState.STARTING
            logger.info(f"Opening camera {self.camera_index} ('{self._device_name}')...")

            # Try CAP_DSHOW on Windows first
            cap = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW)
            if not cap.isOpened():
                logger.debug("CAP_DSHOW failed, falling back to default backend...")
                cap = cv2.VideoCapture(self.camera_index)

            if not cap.isOpened():
                logger.error(f"Failed to open camera index {self.camera_index}")
                self._state = CameraState.ERROR
                self._cap = None
                return False

            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.target_width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.target_height)
            cap.set(cv2.CAP_PROP_FPS, self.target_fps)

            # Test read a frame to confirm operational stream
            ret, test_frame = cap.read()
            if not ret or test_frame is None:
                logger.error("Opened camera handle but read failed on test frame.")
                cap.release()
                self._state = CameraState.ERROR
                self._cap = None
                return False

            self._cap = cap
            self._state = CameraState.RUNNING
            self._consecutive_failures = 0
            logger.info(f"Camera opened successfully: {test_frame.shape[1]}x{test_frame.shape[0]}")
            return True

    def read_frame(self) -> Tuple[bool, Optional[np.ndarray]]:
        """
        Read and preprocess the next frame.
        Handles read failures, low-light detection, and auto-reconnection.
        Returns (success: bool, frame: Optional[np.ndarray]).
        """
        with self._state_lock:
            # Handle disconnected / error auto-recovery
            if self._state in (CameraState.DISCONNECTED, CameraState.ERROR):
                now = time.time()
                if (now - self._last_reconnect_attempt) >= self.reconnect_interval:
                    self._last_reconnect_attempt = now
                    self._state = CameraState.RECOVERING
                    logger.info("Attempting automatic camera recovery...")
                    if self.start():
                        logger.info("Camera recovery successful.")
                        return self.read_frame()
                    else:
                        self._state = CameraState.DISCONNECTED
                return False, None

            if self._cap is None or not self._cap.isOpened():
                return False, None

            ret, frame = self._cap.read()
            if not ret or frame is None:
                self._consecutive_failures += 1
                logger.warning(
                    f"Camera read failure ({self._consecutive_failures}/{self.max_read_failures})"
                )
                if self._consecutive_failures >= self.max_read_failures:
                    logger.error("Camera exceeded max read failures. Marking DISCONNECTED.")
                    self._state = CameraState.DISCONNECTED
                    self._release_raw()
                return False, None

            self._consecutive_failures = 0

            # Low light measurement (mean V channel in HSV)
            try:
                hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
                mean_v = float(np.mean(hsv[:, :, 2]))
                self._is_low_light = mean_v < self.low_light_threshold

                if self._is_low_light and self.clahe_enhancement:
                    # Apply CLAHE to L channel in LAB color space for natural enhancement
                    lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
                    l, a, b = cv2.split(lab)
                    cl = self._clahe.apply(l)
                    merged = cv2.merge((cl, a, b))
                    frame = cv2.cvtColor(merged, cv2.COLOR_LAB2BGR)
            except Exception as enh_err:
                logger.debug(f"Frame enhancement error: {enh_err}")

            return True, frame

    def _release_raw(self) -> None:
        """Internal device release without overriding state."""
        if self._cap is not None:
            try:
                self._cap.release()
            except Exception as exc:
                logger.debug(f"Error releasing VideoCapture: {exc}")
            finally:
                self._cap = None

    def stop(self) -> None:
        """
        Safely stop and release camera hardware.
        Safe to call multiple times.
        """
        with self._state_lock:
            logger.info("Stopping camera...")
            self._release_raw()
            self._state = CameraState.STOPPED
            self._consecutive_failures = 0
            logger.info("Camera stopped cleanly.")

    def set_camera_index(self, new_index: int) -> bool:
        """Switch camera index dynamically."""
        with self._state_lock:
            was_running = self._state == CameraState.RUNNING
            self.stop()
            self.camera_index = new_index
            self._device_name = self._discover_device_name(new_index)
            if was_running:
                return self.start()
            return True
