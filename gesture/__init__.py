"""
gesture package - Hand Tracking, Gesture Recognition, and Vision Controls for SYRAX
"""

from gesture.camera_manager import CameraManager, CameraState
from gesture.hand_tracker import HandResult, HandTracker, LandmarkPoint
from gesture.features import analyze_hand_features, get_palm_center, get_hand_scale, get_normalized_pinch_distance
from gesture.classifier import PoseClassifier, PoseType, classify_static_pose
from gesture.motion import MotionTracker, MotionClassificationResult
from gesture.state_machine import GestureStateMachine, ArmingMode, EngineState
from gesture.calibration import GestureCalibrationWizard, CalibrationData
from gesture.profiles import ProfileManager, AppProfile, GestureActionConfig
from gesture.actions import ActionExecutor, FocusStatus
from gesture.controller import GestureController
from gesture.gesture_engine import GestureEngine

__all__ = [
    "CameraManager",
    "CameraState",
    "HandTracker",
    "HandResult",
    "LandmarkPoint",
    "analyze_hand_features",
    "get_palm_center",
    "get_hand_scale",
    "get_normalized_pinch_distance",
    "PoseClassifier",
    "PoseType",
    "classify_static_pose",
    "MotionTracker",
    "MotionClassificationResult",
    "GestureStateMachine",
    "ArmingMode",
    "EngineState",
    "GestureCalibrationWizard",
    "CalibrationData",
    "ProfileManager",
    "AppProfile",
    "GestureActionConfig",
    "ActionExecutor",
    "FocusStatus",
    "GestureController",
    "GestureEngine",
]
