"""
gesture/gesture_engine.py - High-Level Façade for SYRAX Gesture Intelligence System
Wraps GestureController, providing complete backward-compatibility for AssistantEngine,
GUI Dashboard, and CLI diagnostics, while unlocking modern MediaPipe Tasks tracking,
movement-driven scrolling, and focus-verified application profiles.
"""

import logging
from typing import Optional

import config
from core.event_bus import Events, get_event_bus
from gesture.controller import GestureController
from gesture.state_machine import ArmingMode

logger = logging.getLogger("GestureEngine")


class GestureEngine:
    """
    Central Coordinator Façade for SYRAX vision-based gesture control.
    Preserves existing public API expected by AssistantEngine and Dashboard.
    """

    def __init__(self, camera_index: int = config.CAMERA_INDEX) -> None:
        self._event_bus = get_event_bus()
        self._controller = GestureController()
        if camera_index != self._controller.camera_mgr.camera_index:
            self._controller.camera_mgr.set_camera_index(camera_index)

        # Expose legacy attributes for backwards compatibility
        self._state = config.GESTURE_STATE_IDLE
        self._camera_enabled = True

    @property
    def controller(self) -> GestureController:
        return self._controller

    @property
    def active_backend(self) -> str:
        return self._controller.active_backend

    @property
    def device_name(self) -> str:
        return self._controller.camera_mgr.device_name

    def start(self) -> None:
        """Start background vision loop."""
        self._controller.start()
        self._state = config.GESTURE_STATE_ACTIVE if self._controller.arming_mode == ArmingMode.ARMED else config.GESTURE_STATE_IDLE
        logger.info("GestureEngine façade started.")

    def stop(self) -> None:
        """Stop background vision loop and release webcam."""
        self._controller.stop()
        self._state = config.GESTURE_STATE_IDLE
        logger.info("GestureEngine façade stopped.")

    def enable_camera(self) -> None:
        """Enable camera capture."""
        self._camera_enabled = True
        self._controller.enable_camera()

    def disable_camera(self) -> None:
        """Disable camera capture without affecting voice engine."""
        self._camera_enabled = False
        self._controller.disable_camera()

    def is_camera_enabled(self) -> bool:
        """Return True if camera is capturing."""
        return self._controller.is_camera_enabled

    def get_state(self) -> str:
        """Return ARMED or DISARMED state string for UI pills."""
        return "ACTIVE" if self._controller.arming_mode == ArmingMode.ARMED else "IDLE"

    def set_state(self, new_state: str) -> None:
        """Explicitly switch gesture state (ACTIVE / IDLE)."""
        st = new_state.upper()
        if st in (config.GESTURE_STATE_ACTIVE, "ARMED"):
            self._controller.resume_actions()
            self._state = config.GESTURE_STATE_ACTIVE
        else:
            self._controller.pause_actions()
            self._state = config.GESTURE_STATE_IDLE
        logger.info(f"GestureEngine state set to: {self._state}")
