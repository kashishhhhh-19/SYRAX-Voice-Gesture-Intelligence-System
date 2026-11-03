"""
gesture/controller.py - Central Gesture Orchestrator Thread for SYRAX
Ties together CameraManager, HandTracker, PoseClassifier, MotionTracker,
GestureStateMachine, ProfileManager, ActionExecutor, and CalibrationWizard.
Runs on its own background thread; streams HUD-annotated frames and state telemetry
safely to the EventBus without blocking the UI or Voice Engine.
"""

import logging
import threading
import time
from typing import Dict, Optional, Tuple

import cv2
import numpy as np

from core.event_bus import Events, get_event_bus
from gesture.actions import ActionExecutor
from gesture.calibration import GestureCalibrationWizard
from gesture.camera_manager import CameraManager, CameraState
from gesture.classifier import PoseClassifier, PoseType
from gesture.hand_tracker import HAND_CONNECTIONS, HandResult, HandTracker
from gesture.motion import MotionTracker
from gesture.profiles import ProfileManager
from gesture.state_machine import ArmingMode, EngineState, GestureStateMachine

logger = logging.getLogger("GestureController")


class GestureController:
    """
    Master background controller for vision-based gesture intelligence.
    Runs continuous capture, inference, debounce, and action dispatch on its own thread.
    """

    def __init__(
        self,
        camera_manager: Optional[CameraManager] = None,
        hand_tracker: Optional[HandTracker] = None,
        pose_classifier: Optional[PoseClassifier] = None,
        motion_tracker: Optional[MotionTracker] = None,
        state_machine: Optional[GestureStateMachine] = None,
        profile_manager: Optional[ProfileManager] = None,
        action_executor: Optional[ActionExecutor] = None,
        calibration_wizard: Optional[GestureCalibrationWizard] = None
    ) -> None:
        self.camera_mgr = camera_manager or CameraManager()
        self.tracker = hand_tracker or HandTracker()
        self.classifier = pose_classifier or PoseClassifier()
        self.motion = motion_tracker or MotionTracker()
        self.state_machine = state_machine or GestureStateMachine()
        self.profiles = profile_manager or ProfileManager()
        self.executor = action_executor or ActionExecutor()
        self.calibration = calibration_wizard or GestureCalibrationWizard()

        self._event_bus = get_event_bus()
        self._running = False
        self._camera_enabled = True
        self._worker_thread: Optional[threading.Thread] = None

        # Telemetry cache
        self._last_detected_gesture: str = "NONE"
        self._last_confidence: float = 0.0
        self._active_profile_name: str = "Default"
        self._focus_status: str = "Detected"

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def is_camera_enabled(self) -> bool:
        return self._camera_enabled

    @property
    def active_backend(self) -> str:
        return self.tracker.active_backend

    @property
    def arming_mode(self) -> ArmingMode:
        return self.state_machine.arming_mode

    def start(self) -> None:
        """Start the background vision loop thread."""
        if self._running:
            return
        self._running = True
        self._worker_thread = threading.Thread(
            target=self._run_loop,
            name="SYRAX-Gesture-Controller",
            daemon=True
        )
        self._worker_thread.start()
        logger.info("GestureController background worker started.")

    def stop(self) -> None:
        """Safely stop vision loop and release webcam hardware."""
        self._running = False
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=2.0)
        self.camera_mgr.stop()
        logger.info("GestureController stopped.")

    def enable_camera(self) -> None:
        """Turn on webcam stream."""
        self._camera_enabled = True
        self.camera_mgr.start()
        self._event_bus.emit(
            Events.GESTURE_STATUS_CHANGED,
            status="RUNNING",
            message="Camera enabled. Gesture tracking active."
        )

    def disable_camera(self) -> None:
        """Turn off webcam stream while keeping voice running."""
        self._camera_enabled = False
        self.camera_mgr.stop()
        self._event_bus.emit(
            Events.GESTURE_STATUS_CHANGED,
            status="STOPPED",
            message="Camera stopped. Gesture tracking idle."
        )

    def toggle_arming(self) -> ArmingMode:
        """Toggle between ARMED and DISARMED modes."""
        new_mode = ArmingMode.DISARMED if self.state_machine.arming_mode == ArmingMode.ARMED else ArmingMode.ARMED
        self.state_machine.set_arming_mode(new_mode)
        self._event_bus.emit(
            Events.GESTURE_MODE_TOGGLED,
            state=new_mode.value,
            message=f"Gesture Control: {new_mode.value}"
        )
        return new_mode

    def pause_actions(self) -> None:
        """Temporarily pause gesture actions while keeping preview running."""
        self.state_machine.set_arming_mode(ArmingMode.PAUSED)
        self._event_bus.emit(
            Events.GESTURE_MODE_TOGGLED,
            state="PAUSED",
            message="Gesture Control: PAUSED"
        )

    def resume_actions(self) -> None:
        """Resume gesture actions to ARMED."""
        self.state_machine.set_arming_mode(ArmingMode.ARMED)
        self._event_bus.emit(
            Events.GESTURE_MODE_TOGGLED,
            state="ARMED",
            message="Gesture Control: ARMED"
        )

    def _run_loop(self) -> None:
        """Continuous camera frame capture, inference, and action dispatch loop."""
        while self._running:
            if not self._camera_enabled:
                time.sleep(0.15)
                continue

            # Read frame from CameraManager
            success, raw_frame = self.camera_mgr.read_frame()
            if not success or raw_frame is None:
                time.sleep(0.04)
                continue

            # Mirror frame for selfie perspective
            frame = cv2.flip(raw_frame, 1)

            # Process Hand Tracking
            hands = self.tracker.process(frame)
            hand_detected = len(hands) > 0
            primary_hand: Optional[HandResult] = hands[0] if hand_detected else None

            # Handle Calibration if active
            if self.calibration.is_active and primary_hand:
                adv, prompt = self.calibration.process_frame(primary_hand)
                if adv:
                    self._event_bus.emit(Events.ACTIVITY_LOG, category="CALIBRATION", message=prompt)

            # Static Pose & Dynamic Motion
            coords = [(lm.x, lm.y) for lm in primary_hand.landmarks] if primary_hand else None
            pose_res = self.classifier.process_frame(coords)
            motion_res = self.motion.process_frame(coords, pose_res.pose)

            # Resolve Foreground Window & Application Profile
            hwnd, fg_title, fg_proc = self.executor.get_foreground_window_info()
            profile = self.profiles.resolve_profile(fg_proc, fg_title)
            self._active_profile_name = profile.name

            # Determine Candidate Gesture
            candidate_gesture = motion_res.gesture or (pose_res.pose if pose_res.pose not in (PoseType.UNKNOWN, PoseType.NONE) else None)
            confidence = motion_res.confidence if motion_res.gesture else pose_res.confidence

            # Step State Machine
            palm_center = primary_hand.palm_center_norm if primary_hand else (0.5, 0.5)
            sm_out = self.state_machine.process_step(
                hand_detected=hand_detected,
                static_pose=pose_res.pose,
                motion_gesture=motion_res.gesture,
                palm_center=palm_center,
                scroll_delta=motion_res.scroll_delta,
                is_continuous=motion_res.is_continuous
            )

            # Action Execution Gate
            if sm_out.should_execute and sm_out.gesture_name:
                action_name = sm_out.gesture_name
                self._last_detected_gesture = action_name
                self._last_confidence = confidence

                if action_name == "FIST_TOGGLE":
                    self.toggle_arming()
                else:
                    action_cfg = self.profiles.get_action_for_gesture(profile, action_name)
                    if action_cfg:
                        if action_cfg.command == "pause_actions":
                            self.pause_actions()
                        else:
                            exec_ok, exec_desc = self.executor.execute_action(
                                action_type=action_cfg.action_type,
                                keys=action_cfg.keys,
                                direction=action_cfg.direction,
                                scroll_delta=sm_out.scroll_delta,
                                expected_profile_name=profile.name
                            )
                            if exec_ok:
                                self._event_bus.emit(
                                    Events.ACTIVITY_LOG,
                                    category="GESTURE",
                                    message=f"[{profile.name}] Executed: {action_name} -> {action_cfg.description}"
                                )

            # Render HUD on frame
            annotated = self._render_hud(
                frame=frame,
                hand=primary_hand,
                gesture_name=candidate_gesture or "NONE",
                confidence=confidence,
                profile_name=profile.name,
                arming_mode=self.state_machine.arming_mode,
                cooldown_ms=sm_out.cooldown_remaining_ms
            )

            # Emit preview frame to GUI (converting BGR -> RGB)
            rgb_preview = cv2.cvtColor(annotated, cv2.COLOR_BGR2RGB)
            self._event_bus.emit(
                Events.GESTURE_FRAME,
                frame=rgb_preview,
                hand_detected=hand_detected,
                gesture=candidate_gesture or "NONE",
                confidence=confidence,
                state=self.state_machine.arming_mode.value,
                backend=self.tracker.active_backend,
                profile=profile.name,
                cooldown_ms=sm_out.cooldown_remaining_ms,
                device_name=self.camera_mgr.device_name
            )

            # Throttle to ~25-30 FPS
            time.sleep(0.03)

        self.camera_mgr.stop()

    def _render_hud(
        self,
        frame: np.ndarray,
        hand: Optional[HandResult],
        gesture_name: str,
        confidence: float,
        profile_name: str,
        arming_mode: ArmingMode,
        cooldown_ms: int
    ) -> np.ndarray:
        """Render high-tech HUD visualizer on preview frame."""
        vis = frame.copy()
        h, w = vis.shape[:2]

        # Draw Skeleton and Bounding Box
        if hand:
            if not hand.is_fallback:
                # MediaPipe Landmark Points & Connections
                for pt1_idx, pt2_idx in HAND_CONNECTIONS:
                    if pt1_idx < len(hand.landmarks) and pt2_idx < len(hand.landmarks):
                        p1 = (hand.landmarks[pt1_idx].px, hand.landmarks[pt1_idx].py)
                        p2 = (hand.landmarks[pt2_idx].px, hand.landmarks[pt2_idx].py)
                        cv2.line(vis, p1, p2, (0, 200, 255), 2)

                for lm in hand.landmarks:
                    cv2.circle(vis, (lm.px, lm.py), 4, (0, 255, 128), -1)
            else:
                # Fallback Notice
                cv2.putText(
                    vis, "OpenCV Fallback Mode (No Skeleton)",
                    (15, h - 35), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 165, 255), 1
                )

            # Bounding box
            bx1, by1, bx2, by2 = hand.bbox_pixel
            cv2.rectangle(vis, (bx1, by1), (bx2, by2), (255, 100, 0), 1)

            # Handedness tag
            cv2.putText(
                vis, f"{hand.handedness} Hand",
                (bx1, max(15, by1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 200, 0), 1
            )

        # Top Banner: HUD readout
        hud_bg = vis[0:36, 0:w]
        cv2.rectangle(vis, (0, 0), (w, 36), (15, 15, 25), -1)

        mode_color = (0, 255, 100) if arming_mode == ArmingMode.ARMED else (0, 100, 255)
        cv2.putText(
            vis, f"[{arming_mode.value}]",
            (8, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.55, mode_color, 2
        )

        cv2.putText(
            vis, f"App: {profile_name}",
            (115, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1
        )

        if gesture_name and gesture_name != "NONE":
            g_txt = f"{gesture_name} ({int(confidence*100)}%)"
            cv2.putText(
                vis, g_txt,
                (w - 220, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 240, 255), 1
            )

        # Low light indicator
        if self.camera_mgr.is_low_light:
            cv2.putText(
                vis, "LOW LIGHT [CLAHE ON]",
                (8, h - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (0, 255, 255), 1
            )

        return vis
