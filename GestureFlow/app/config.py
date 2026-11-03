"""
GestureFlow - Configuration Module
Defines settings for camera capture, hand tracking, gesture thresholds,
timing cooldowns, safety controls, and UI theme attributes.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, Tuple


@dataclass
class CameraConfig:
    """Settings for OpenCV video capture."""
    camera_index: int = 0
    fallback_indices: Tuple[int, ...] = (1, 2)
    frame_width: int = 640
    frame_height: int = 480
    target_fps: int = 30
    mirror_frame: bool = True
    auto_reconnect: bool = True
    reconnect_interval_sec: float = 2.0


@dataclass
class TrackingConfig:
    """Settings for MediaPipe Hands detection & tracking."""
    max_num_hands: int = 2
    min_detection_confidence: float = 0.70
    min_tracking_confidence: float = 0.60
    model_complexity: int = 1


@dataclass
class GestureThresholds:
    """
    Mathematical and geometric thresholds for gesture classification.
    Distances are normalized to hand bounding box or frame dimensions.
    """
    # Swipe detection parameters
    swipe_min_displacement_x: float = 0.14       # Normalized horizontal movement across frame
    swipe_min_velocity: float = 0.38             # Normalized velocity (units/sec)
    swipe_max_displacement_y: float = 0.12       # Maximum allowed vertical drift for a horizontal swipe
    swipe_history_frames: int = 10               # Sliding window size (~300ms at 30fps)
    swipe_stationary_velocity: float = 0.08      # Velocity below which hand is definitely stationary

    # Static finger angle & extension
    pointing_vertical_tolerance_deg: float = 35.0 # Max degrees from true vertical (up or down)
    finger_curl_threshold: float = 1.05          # Ratio of tip-to-wrist vs pip-to-wrist for curled finger
    finger_extended_threshold: float = 1.25      # Ratio of tip-to-wrist vs pip-to-wrist for extended finger

    # Pinch and Zoom
    pinch_in_distance: float = 0.07              # Normalized distance between thumb tip and index tip
    pinch_out_distance: float = 0.18             # Normalized distance for pinch-out (zoom in)
    pinch_spread_delta: float = 0.06             # Delta expansion required to confirm pinch-out

    # Consecutive frame stability requirement
    stability_required_frames: int = 3           # Required consecutive matching frames for static gestures


@dataclass
class CooldownConfig:
    """Cooldown durations in seconds to avoid accidental repeated actions."""
    default_cooldown: float = 0.60
    swipe_cooldown: float = 0.75
    zoom_cooldown: float = 0.45
    scroll_cooldown: float = 0.20
    mode_toggle_cooldown: float = 1.00


@dataclass
class ControlConfig:
    """Safety and computer control settings."""
    enabled_by_default: bool = False
    pyautogui_failsafe: bool = True
    pyautogui_pause: float = 0.02
    scroll_amount: int = 180                     # Pixels per scroll step
    emergency_stop_keys: Tuple[str, ...] = ("esc", "q")


class UITheme:
    """Modern dark theme with restrained professional blue accents."""
    BG_ROOT = "#0f172a"          # Slate 900
    BG_CARD = "#1e293b"          # Slate 800
    BG_CARD_LIGHT = "#334155"    # Slate 700
    BG_CANVAS = "#020617"        # Slate 950
    BORDER_COLOR = "#334155"     # Slate 700

    ACCENT_PRIMARY = "#2563eb"   # Royal Blue 600
    ACCENT_HOVER = "#1d4ed8"     # Blue 700
    ACCENT_ACTIVE = "#3b82f6"    # Blue 500

    SUCCESS = "#10b981"          # Emerald 500
    SUCCESS_BG = "#064e3b"       # Emerald 900
    WARNING = "#f59e0b"          # Amber 500
    WARNING_BG = "#78350f"       # Amber 900
    DANGER = "#ef4444"           # Red 500
    DANGER_HOVER = "#dc2626"     # Red 600
    DANGER_BG = "#7f1d1d"        # Red 900

    TEXT_PRIMARY = "#f8fafc"     # Slate 50
    TEXT_MUTED = "#94a3b8"       # Slate 400
    TEXT_DIM = "#64748b"         # Slate 500

    FONT_FAMILY = "Segoe UI"


@dataclass
class AppConfig:
    """Root configuration aggregator."""
    camera: CameraConfig = field(default_factory=CameraConfig)
    tracking: TrackingConfig = field(default_factory=TrackingConfig)
    thresholds: GestureThresholds = field(default_factory=GestureThresholds)
    cooldown: CooldownConfig = field(default_factory=CooldownConfig)
    control: ControlConfig = field(default_factory=ControlConfig)
    theme: UITheme = field(default_factory=UITheme)


# Default global configuration instance
DEFAULT_CONFIG = AppConfig()
