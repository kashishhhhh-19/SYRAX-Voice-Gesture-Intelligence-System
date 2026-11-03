"""
gesture/state_machine.py - Debounce, Arming, Hold-Times, Cooldowns & Neutral Position Gating
Maintains formal state transitions:
IDLE -> HAND_PRESENT -> POSE_CANDIDATE -> POSE_CONFIRMED -> ACTION_FIRED -> COOLDOWN
Enforces ARMED / DISARMED / PAUSED states, release-before-refire, and neutral-zone re-arming.
"""

import enum
import math
import time
from dataclasses import dataclass
from typing import Dict, Optional, Tuple


class EngineState(enum.Enum):
    IDLE = "IDLE"                        # No hand detected
    HAND_PRESENT = "HAND_PRESENT"        # Hand detected, assessing stability
    POSE_CANDIDATE = "POSE_CANDIDATE"    # Pose detected, accumulating hold frames
    POSE_CONFIRMED = "POSE_CONFIRMED"    # Pose meets hold requirements
    ACTION_FIRED = "ACTION_FIRED"        # Action emitted to executor
    COOLDOWN = "COOLDOWN"                # Enforcing cooldown delay


class ArmingMode(enum.Enum):
    ARMED = "ARMED"                      # Gestures execute computer actions
    DISARMED = "DISARMED"                # Gestures recognized on HUD, but actions blocked
    PAUSED = "PAUSED"                    # Temporarily paused by Open Palm or user voice


@dataclass
class StateMachineOutput:
    """Evaluated action recommendation from the state machine."""
    should_execute: bool
    gesture_name: Optional[str]
    engine_state: EngineState
    arming_mode: ArmingMode
    cooldown_remaining_ms: int
    is_continuous: bool = False
    scroll_delta: int = 0
    feedback_message: str = ""


class GestureStateMachine:
    """
    Coordinates debouncing, arming modes, per-gesture cooldowns,
    release-before-refire gating, and neutral-zone re-arming.
    """

    def __init__(
        self,
        fist_hold_ms: int = 950,
        palm_hold_ms: int = 450,
        swipe_cooldown_ms: int = 800,
        play_pause_cooldown_ms: int = 1200,
        zoom_cooldown_ms: int = 400,
        fist_toggle_cooldown_ms: int = 1500,
        general_cooldown_ms: int = 600,
        neutral_return_threshold: float = 0.16,
        require_neutral_position: bool = True,
        start_armed: bool = True,
        neutral_palm_center: Tuple[float, float] = (0.5, 0.6)
    ) -> None:
        self.fist_hold_sec = fist_hold_ms / 1000.0
        self.palm_hold_sec = palm_hold_ms / 1000.0
        self.swipe_cooldown_sec = swipe_cooldown_ms / 1000.0
        self.play_pause_cooldown_sec = play_pause_cooldown_ms / 1000.0
        self.zoom_cooldown_sec = zoom_cooldown_ms / 1000.0
        self.fist_toggle_cooldown_sec = fist_toggle_cooldown_ms / 1000.0
        self.general_cooldown_sec = general_cooldown_ms / 1000.0
        self.neutral_threshold = neutral_return_threshold
        self.require_neutral = require_neutral_position
        self.neutral_center = neutral_palm_center

        self.engine_state = EngineState.IDLE
        self.arming_mode = ArmingMode.ARMED if start_armed else ArmingMode.DISARMED

        # Pose hold timers
        self._current_pose: Optional[str] = None
        self._pose_start_time: float = 0.0

        # Last executed gesture & release gating
        self._last_fired_gesture: Optional[str] = None
        self._has_released: bool = True
        self._has_returned_to_neutral: bool = True

        # Cooldown tracking
        self._last_trigger_times: Dict[str, float] = {}

    def set_neutral_center(self, center: Tuple[float, float]) -> None:
        """Update neutral resting position from user calibration."""
        self.neutral_center = center

    def set_arming_mode(self, mode: ArmingMode) -> None:
        """Switch arming mode (ARMED / DISARMED / PAUSED)."""
        self.arming_mode = mode

    def is_cooling_down(self, gesture: str, now: float) -> Tuple[bool, int]:
        """Check if gesture is within its cooldown window; returns (is_cooldown, remaining_ms)."""
        cooldown_limit = self.general_cooldown_sec
        if "SWIPE" in gesture:
            cooldown_limit = self.swipe_cooldown_sec
        elif "OPEN_PALM" in gesture or "PLAY_PAUSE" in gesture:
            cooldown_limit = self.play_pause_cooldown_sec
        elif "PINCH" in gesture or "ZOOM" in gesture:
            cooldown_limit = self.zoom_cooldown_sec
        elif "FIST" in gesture:
            cooldown_limit = self.fist_toggle_cooldown_sec

        last_time = self._last_trigger_times.get(gesture, 0.0)
        elapsed = now - last_time
        if elapsed < cooldown_limit:
            rem_ms = int((cooldown_limit - elapsed) * 1000)
            return True, rem_ms
        return False, 0

    def record_trigger(self, gesture: str, now: float) -> None:
        """Record timestamp of executed action and mark release required."""
        self._last_trigger_times[gesture] = now
        self._last_fired_gesture = gesture
        self._has_released = False
        self._has_returned_to_neutral = False
        self.engine_state = EngineState.COOLDOWN

    def reset_hand_presence(self) -> None:
        """Called when no hand is visible in frame."""
        self.engine_state = EngineState.IDLE
        self._current_pose = None
        self._pose_start_time = 0.0
        self._has_released = True
        self._has_returned_to_neutral = True

    def process_step(
        self,
        hand_detected: bool,
        static_pose: str,
        motion_gesture: Optional[str],
        palm_center: Tuple[float, float],
        scroll_delta: int = 0,
        is_continuous: bool = False,
        current_time: Optional[float] = None
    ) -> StateMachineOutput:
        """
        Step the state machine with current frame observations.
        Returns StateMachineOutput deciding whether to execute an action.
        """
        now = time.time() if current_time is None else current_time

        if not hand_detected:
            self.reset_hand_presence()
            return StateMachineOutput(
                should_execute=False,
                gesture_name=None,
                engine_state=EngineState.IDLE,
                arming_mode=self.arming_mode,
                cooldown_remaining_ms=0,
                feedback_message="No hand present"
            )

        self.engine_state = EngineState.HAND_PRESENT

        # Neutral position tracking:
        dist_to_neutral = math.hypot(palm_center[0] - self.neutral_center[0], palm_center[1] - self.neutral_center[1])
        if dist_to_neutral <= self.neutral_threshold:
            self._has_returned_to_neutral = True

        # Check release gating:
        if static_pose != self._last_fired_gesture and motion_gesture is None:
            self._has_released = True

        # ======================================================================
        # 1. ARMING TOGGLE (Fist Hold ~0.95s)
        # Fist toggles ARMED <-> DISARMED regardless of current arming mode
        # ======================================================================
        if static_pose == "FIST":
            if self._current_pose == "FIST":
                hold_duration = now - self._pose_start_time
            else:
                self._current_pose = "FIST"
                self._pose_start_time = now
                hold_duration = 0.0

            if hold_duration >= self.fist_hold_sec:
                on_cd, rem = self.is_cooling_down("FIST_TOGGLE", now)
                if not on_cd and self._has_released:
                    # Toggle arming
                    new_mode = ArmingMode.DISARMED if self.arming_mode == ArmingMode.ARMED else ArmingMode.ARMED
                    self.set_arming_mode(new_mode)
                    self.record_trigger("FIST_TOGGLE", now)
                    self._pose_start_time = now
                    return StateMachineOutput(
                        should_execute=True,
                        gesture_name="FIST_TOGGLE",
                        engine_state=EngineState.ACTION_FIRED,
                        arming_mode=self.arming_mode,
                        cooldown_remaining_ms=int(self.fist_toggle_cooldown_sec * 1000),
                        feedback_message=f"Gesture Control toggled to {self.arming_mode.value}"
                    )
            return StateMachineOutput(
                should_execute=False,
                gesture_name="FIST",
                engine_state=EngineState.POSE_CANDIDATE,
                arming_mode=self.arming_mode,
                cooldown_remaining_ms=0,
                feedback_message=f"Holding Fist ({int(hold_duration*1000)}ms)"
            )
        else:
            if self._current_pose == "FIST":
                self._current_pose = None

        # ======================================================================
        # 2. CONTINUOUS SCROLLING (MOVEMENT-DRIVEN)
        # Scrolling does not require arming release check, but respects ARMED mode
        # ======================================================================
        if is_continuous and scroll_delta != 0 and motion_gesture in ("ONE_FINGER_UP", "ONE_FINGER_DOWN"):
            if self.arming_mode != ArmingMode.ARMED:
                return StateMachineOutput(
                    should_execute=False,
                    gesture_name=motion_gesture,
                    engine_state=EngineState.HAND_PRESENT,
                    arming_mode=self.arming_mode,
                    cooldown_remaining_ms=0,
                    scroll_delta=scroll_delta,
                    is_continuous=True,
                    feedback_message="Scrolling blocked (Disarmed/Paused)"
                )

            return StateMachineOutput(
                should_execute=True,
                gesture_name=motion_gesture,
                engine_state=EngineState.ACTION_FIRED,
                arming_mode=self.arming_mode,
                cooldown_remaining_ms=0,
                is_continuous=True,
                scroll_delta=scroll_delta,
                feedback_message=f"Scroll {motion_gesture}: {scroll_delta:+d}"
            )

        # ======================================================================
        # 3. DYNAMIC MOTION GESTURES (Swipes, Pinch Zoom, Two-Fingers)
        # Requires neutral return (blocks return-stroke of swipe)
        # ======================================================================
        if motion_gesture:
            if self.require_neutral and not self._has_returned_to_neutral:
                return StateMachineOutput(
                    should_execute=False,
                    gesture_name=motion_gesture,
                    engine_state=EngineState.COOLDOWN,
                    arming_mode=self.arming_mode,
                    cooldown_remaining_ms=0,
                    feedback_message="Return hand to neutral before next swipe"
                )

            on_cd, rem = self.is_cooling_down(motion_gesture, now)
            if on_cd:
                return StateMachineOutput(
                    should_execute=False,
                    gesture_name=motion_gesture,
                    engine_state=EngineState.COOLDOWN,
                    arming_mode=self.arming_mode,
                    cooldown_remaining_ms=rem,
                    feedback_message=f"Cooldown ({rem}ms)"
                )

            if not self._has_released and motion_gesture == self._last_fired_gesture:
                return StateMachineOutput(
                    should_execute=False,
                    gesture_name=motion_gesture,
                    engine_state=EngineState.COOLDOWN,
                    arming_mode=self.arming_mode,
                    cooldown_remaining_ms=0,
                    feedback_message="Release gesture before repeat"
                )

            if self.arming_mode != ArmingMode.ARMED:
                return StateMachineOutput(
                    should_execute=False,
                    gesture_name=motion_gesture,
                    engine_state=EngineState.HAND_PRESENT,
                    arming_mode=self.arming_mode,
                    cooldown_remaining_ms=0,
                    feedback_message="Action blocked (Disarmed/Paused)"
                )

            self.record_trigger(motion_gesture, now)
            return StateMachineOutput(
                should_execute=True,
                gesture_name=motion_gesture,
                engine_state=EngineState.ACTION_FIRED,
                arming_mode=self.arming_mode,
                cooldown_remaining_ms=int(self.swipe_cooldown_sec * 1000),
                feedback_message=f"Fired: {motion_gesture}"
            )

        # ======================================================================
        # 4. STATIC STEADY POSES (OPEN_PALM Play/Pause)
        # Requires steady hold ~0.45s
        # ======================================================================
        if static_pose == "OPEN_PALM":
            if self._current_pose == "OPEN_PALM":
                hold_duration = now - self._pose_start_time
            else:
                self._current_pose = "OPEN_PALM"
                self._pose_start_time = now
                hold_duration = 0.0

            if hold_duration >= self.palm_hold_sec:
                on_cd, rem = self.is_cooling_down("OPEN_PALM", now)
                if on_cd:
                    return StateMachineOutput(
                        should_execute=False,
                        gesture_name="OPEN_PALM",
                        engine_state=EngineState.COOLDOWN,
                        arming_mode=self.arming_mode,
                        cooldown_remaining_ms=rem,
                        feedback_message=f"Open Palm Cooldown ({rem}ms)"
                    )

                if not self._has_released and self._last_fired_gesture == "OPEN_PALM":
                    return StateMachineOutput(
                        should_execute=False,
                        gesture_name="OPEN_PALM",
                        engine_state=EngineState.POSE_CONFIRMED,
                        arming_mode=self.arming_mode,
                        cooldown_remaining_ms=0,
                        feedback_message="Open Palm held (release to refire)"
                    )

                if self.arming_mode != ArmingMode.ARMED:
                    return StateMachineOutput(
                        should_execute=False,
                        gesture_name="OPEN_PALM",
                        engine_state=EngineState.POSE_CONFIRMED,
                        arming_mode=self.arming_mode,
                        cooldown_remaining_ms=0,
                        feedback_message="Open Palm blocked (Disarmed/Paused)"
                    )

                self.record_trigger("OPEN_PALM", now)
                self._pose_start_time = now
                return StateMachineOutput(
                    should_execute=True,
                    gesture_name="OPEN_PALM",
                    engine_state=EngineState.ACTION_FIRED,
                    arming_mode=self.arming_mode,
                    cooldown_remaining_ms=int(self.play_pause_cooldown_sec * 1000),
                    feedback_message="Fired: OPEN_PALM"
                )
            else:
                return StateMachineOutput(
                    should_execute=False,
                    gesture_name="OPEN_PALM",
                    engine_state=EngineState.POSE_CANDIDATE,
                    arming_mode=self.arming_mode,
                    cooldown_remaining_ms=0,
                    feedback_message=f"Holding Open Palm ({int(hold_duration*1000)}ms)"
                )
        else:
            if self._current_pose == "OPEN_PALM":
                self._current_pose = None

        return StateMachineOutput(
            should_execute=False,
            gesture_name=static_pose if static_pose != "UNKNOWN" else None,
            engine_state=EngineState.HAND_PRESENT,
            arming_mode=self.arming_mode,
            cooldown_remaining_ms=0,
            feedback_message=f"Pose: {static_pose}"
        )
