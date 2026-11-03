"""
GestureFlow - Desktop User Interface Module
Builds a desktop application with webcam preview,
telemetry HUD, activity logs, reference cards, and safety controls.
Supports CustomTkinter with graceful fallback to standard Tkinter.
"""

import math
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional, Tuple
import cv2
from PIL import Image, ImageTk

try:
    import customtkinter as ctk
    ctk.set_appearance_mode("Dark")
    ctk.set_default_color_theme("blue")
    CTK_AVAILABLE = True
except ImportError:
    ctk = None
    CTK_AVAILABLE = False

from app.camera import CameraManager, CameraStatus
from app.config import AppConfig, DEFAULT_CONFIG, UITheme
from app.gesture_controller import ActionLogEntry, ControlMode, GestureController
from app.gesture_recognition import GestureRecognizer, GestureResult, GestureType
from app.hand_tracking import HandTracker


class GestureFlowApp:
    """
    Main desktop GUI application for GestureFlow.
    Orchestrates the camera pipeline, hand tracking, gesture recognizer,
    computer controller, and real-time dashboard display.
    """

    def __init__(self, config: Optional[AppConfig] = None):
        self.config = config or DEFAULT_CONFIG
        self.theme = self.config.theme

        # Core CV and Control Subsystems
        self.camera = CameraManager(self.config.camera)
        self.tracker = HandTracker(self.config.tracking)
        self.recognizer = GestureRecognizer(self.config.thresholds, self.config.cooldown)
        self.controller = GestureController(
            config=self.config.control,
            on_action_callback=self._on_action_executed
        )

        # Performance & session statistics
        self.session_start_time = time.time()
        self.total_frames_processed = 0
        self.total_gestures_detected = 0

        # UI Window Setup
        self._init_window()
        self._build_header()
        self._build_main_content()
        self._build_footer()
        self._bind_shortcuts()

        # Frame loop flag & multi-threading
        self._is_active = True
        self._loop_delay_ms = 16  # ~60 fps UI poll rate
        self._frame_lock = threading.Lock()
        self._latest_frame_data: Optional[Tuple[np.ndarray, list, GestureResult]] = None

        # Start dedicated background CV perception worker thread
        # Decouples video capture & MediaPipe inference from UI event loop
        self._worker_thread = threading.Thread(
            target=self._capture_and_perception_worker,
            daemon=True,
            name="GestureFlowCVWorker"
        )
        self._worker_thread.start()

        # Initial log
        self._log_message("System", "GestureFlow AI Engine initialized. Computer controls disabled by default for safety.")

    def _init_window(self):
        """Creates the root window using CustomTkinter or Tkinter."""
        if CTK_AVAILABLE:
            self.root = ctk.CTk()
        else:
            self.root = tk.Tk()

        self.root.title("GestureFlow — AI Hand Gesture Controller")
        self.root.geometry("1180x820")
        self.root.minsize(1040, 720)
        self.root.configure(bg=self.theme.BG_ROOT)

        # Handle clean exit on close
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def _build_header(self):
        """Builds top branding bar and status badges."""
        if CTK_AVAILABLE:
            header_frame = ctk.CTkFrame(self.root, fg_color=self.theme.BG_CARD, corner_radius=0, height=64)
        else:
            header_frame = tk.Frame(self.root, bg=self.theme.BG_CARD, height=64)
        header_frame.pack(fill="x", side="top", padx=0, pady=0)

        # Left branding
        brand_box = ctk.CTkFrame(header_frame, fg_color="transparent") if CTK_AVAILABLE else tk.Frame(header_frame, bg=self.theme.BG_CARD)
        brand_box.pack(side="left", padx=20, pady=10)

        title_lbl = ctk.CTkLabel(
            brand_box,
            text="⚡ GestureFlow",
            font=ctk.CTkFont(family=self.theme.FONT_FAMILY, size=22, weight="bold"),
            text_color=self.theme.TEXT_PRIMARY
        ) if CTK_AVAILABLE else tk.Label(
            brand_box,
            text="⚡ GestureFlow",
            font=(self.theme.FONT_FAMILY, 20, "bold"),
            fg=self.theme.TEXT_PRIMARY,
            bg=self.theme.BG_CARD
        )
        title_lbl.pack(side="left")

        subtitle_lbl = ctk.CTkLabel(
            brand_box,
            text="  |  AI Hand Gesture Controller",
            font=ctk.CTkFont(family=self.theme.FONT_FAMILY, size=13),
            text_color=self.theme.TEXT_MUTED
        ) if CTK_AVAILABLE else tk.Label(
            brand_box,
            text="  |  AI Hand Gesture Controller",
            font=(self.theme.FONT_FAMILY, 11),
            fg=self.theme.TEXT_MUTED,
            bg=self.theme.BG_CARD
        )
        subtitle_lbl.pack(side="left")

        # Right status badges
        status_box = ctk.CTkFrame(header_frame, fg_color="transparent") if CTK_AVAILABLE else tk.Frame(header_frame, bg=self.theme.BG_CARD)
        status_box.pack(side="right", padx=20, pady=10)

        # Camera Status Badge
        self.camera_badge = ctk.CTkLabel(
            status_box,
            text="● CAMERA: OFF",
            font=ctk.CTkFont(family=self.theme.FONT_FAMILY, size=11, weight="bold"),
            fg_color=self.theme.BG_CARD_LIGHT,
            text_color=self.theme.TEXT_MUTED,
            corner_radius=6,
            padx=10,
            pady=4
        ) if CTK_AVAILABLE else tk.Label(
            status_box,
            text="● CAMERA: OFF",
            font=(self.theme.FONT_FAMILY, 10, "bold"),
            fg=self.theme.TEXT_MUTED,
            bg=self.theme.BG_CARD_LIGHT,
            padx=8,
            pady=3
        )
        self.camera_badge.pack(side="left", padx=5)

        # Control Safety Badge
        self.control_badge = ctk.CTkLabel(
            status_box,
            text="🔒 CONTROLS: DISABLED (SAFE)",
            font=ctk.CTkFont(family=self.theme.FONT_FAMILY, size=11, weight="bold"),
            fg_color=self.theme.WARNING_BG,
            text_color=self.theme.WARNING,
            corner_radius=6,
            padx=10,
            pady=4
        ) if CTK_AVAILABLE else tk.Label(
            status_box,
            text="🔒 CONTROLS: DISABLED (SAFE)",
            font=(self.theme.FONT_FAMILY, 10, "bold"),
            fg=self.theme.WARNING,
            bg=self.theme.WARNING_BG,
            padx=8,
            pady=3
        )
        self.control_badge.pack(side="left", padx=5)

    def _build_main_content(self):
        """Constructs split-screen layout: Video preview & control panel."""
        if CTK_AVAILABLE:
            main_container = ctk.CTkFrame(self.root, fg_color="transparent")
        else:
            main_container = tk.Frame(self.root, bg=self.theme.BG_ROOT)
        main_container.pack(fill="both", expand=True, padx=16, pady=12)

        # ----------------- LEFT COLUMN: VIDEO FEED & PRIMARY CONTROLS -----------------
        left_col = ctk.CTkFrame(main_container, fg_color="transparent") if CTK_AVAILABLE else tk.Frame(main_container, bg=self.theme.BG_ROOT)
        left_col.pack(side="left", fill="both", expand=True, padx=(0, 10))

        # Video Preview Card
        video_card = ctk.CTkFrame(left_col, fg_color=self.theme.BG_CARD, corner_radius=12) if CTK_AVAILABLE else tk.Frame(left_col, bg=self.theme.BG_CARD)
        video_card.pack(fill="both", expand=True, pady=(0, 10))

        # Video Canvas
        self.video_label = tk.Label(
            video_card,
            text="Webcam feed not started.\nClick 'Start Camera' below to begin real-time tracking.",
            font=(self.theme.FONT_FAMILY, 13),
            fg=self.theme.TEXT_MUTED,
            bg=self.theme.BG_CANVAS
        )
        self.video_label.pack(fill="both", expand=True, padx=10, pady=10)

        # HUD Overlay Bar (under preview)
        hud_bar = ctk.CTkFrame(video_card, fg_color=self.theme.BG_CARD_LIGHT, corner_radius=8, height=36) if CTK_AVAILABLE else tk.Frame(video_card, bg=self.theme.BG_CARD_LIGHT, height=36)
        hud_bar.pack(fill="x", padx=10, pady=(0, 10))

        self.hud_gesture_lbl = ctk.CTkLabel(
            hud_bar,
            text="Detected: None",
            font=ctk.CTkFont(family=self.theme.FONT_FAMILY, size=12, weight="bold"),
            text_color=self.theme.ACCENT_ACTIVE
        ) if CTK_AVAILABLE else tk.Label(
            hud_bar,
            text="Detected: None",
            font=(self.theme.FONT_FAMILY, 11, "bold"),
            fg=self.theme.ACCENT_ACTIVE,
            bg=self.theme.BG_CARD_LIGHT
        )
        self.hud_gesture_lbl.pack(side="left", padx=12, pady=4)

        self.hud_telemetry_lbl = ctk.CTkLabel(
            hud_bar,
            text="FPS: 0.0  |  Hands: 0",
            font=ctk.CTkFont(family=self.theme.FONT_FAMILY, size=11),
            text_color=self.theme.TEXT_MUTED
        ) if CTK_AVAILABLE else tk.Label(
            hud_bar,
            text="FPS: 0.0  |  Hands: 0",
            font=(self.theme.FONT_FAMILY, 10),
            fg=self.theme.TEXT_MUTED,
            bg=self.theme.BG_CARD_LIGHT
        )
        self.hud_telemetry_lbl.pack(side="right", padx=12, pady=4)

        # Primary Control Bar
        control_bar = ctk.CTkFrame(left_col, fg_color=self.theme.BG_CARD, corner_radius=12) if CTK_AVAILABLE else tk.Frame(left_col, bg=self.theme.BG_CARD)
        control_bar.pack(fill="x", pady=0)

        btn_row = ctk.CTkFrame(control_bar, fg_color="transparent") if CTK_AVAILABLE else tk.Frame(control_bar, bg=self.theme.BG_CARD)
        btn_row.pack(fill="x", padx=12, pady=10)

        # Camera Button
        self.btn_camera = ctk.CTkButton(
            btn_row,
            text="▶ Start Camera",
            font=ctk.CTkFont(family=self.theme.FONT_FAMILY, size=12, weight="bold"),
            fg_color=self.theme.ACCENT_PRIMARY,
            hover_color=self.theme.ACCENT_HOVER,
            command=self.toggle_camera,
            width=130,
            height=36
        ) if CTK_AVAILABLE else tk.Button(
            btn_row,
            text="▶ Start Camera",
            font=(self.theme.FONT_FAMILY, 11, "bold"),
            fg=self.theme.TEXT_PRIMARY,
            bg=self.theme.ACCENT_PRIMARY,
            command=self.toggle_camera,
            relief="flat",
            padx=10,
            pady=6
        )
        self.btn_camera.pack(side="left", padx=(0, 8))

        # Enable/Disable Controls Button
        self.btn_controls = ctk.CTkButton(
            btn_row,
            text="🛡️ Enable Controls",
            font=ctk.CTkFont(family=self.theme.FONT_FAMILY, size=12, weight="bold"),
            fg_color=self.theme.SUCCESS,
            hover_color="#059669",
            command=self.toggle_controls,
            width=140,
            height=36
        ) if CTK_AVAILABLE else tk.Button(
            btn_row,
            text="🛡️ Enable Controls",
            font=(self.theme.FONT_FAMILY, 11, "bold"),
            fg=self.theme.TEXT_PRIMARY,
            bg=self.theme.SUCCESS,
            command=self.toggle_controls,
            relief="flat",
            padx=10,
            pady=6
        )
        self.btn_controls.pack(side="left", padx=8)

        # Emergency Stop Button
        self.btn_emergency = ctk.CTkButton(
            btn_row,
            text="🛑 EMERGENCY STOP",
            font=ctk.CTkFont(family=self.theme.FONT_FAMILY, size=12, weight="bold"),
            fg_color=self.theme.DANGER,
            hover_color=self.theme.DANGER_HOVER,
            command=self.trigger_emergency_stop,
            width=160,
            height=36
        ) if CTK_AVAILABLE else tk.Button(
            btn_row,
            text="🛑 EMERGENCY STOP",
            font=(self.theme.FONT_FAMILY, 11, "bold"),
            fg=self.theme.TEXT_PRIMARY,
            bg=self.theme.DANGER,
            command=self.trigger_emergency_stop,
            relief="flat",
            padx=10,
            pady=6
        )
        self.btn_emergency.pack(side="left", padx=8)

        # Mode Selection
        mode_lbl = ctk.CTkLabel(
            btn_row,
            text="Mode:",
            font=ctk.CTkFont(family=self.theme.FONT_FAMILY, size=12, weight="bold"),
            text_color=self.theme.TEXT_MUTED
        ) if CTK_AVAILABLE else tk.Label(
            btn_row,
            text="Mode:",
            font=(self.theme.FONT_FAMILY, 10, "bold"),
            fg=self.theme.TEXT_MUTED,
            bg=self.theme.BG_CARD
        )
        mode_lbl.pack(side="left", padx=(16, 6))

        mode_options = [
            ControlMode.UNIFIED.value,
            ControlMode.PRESENTATION.value,
            ControlMode.SCROLLING.value
        ]
        if CTK_AVAILABLE:
            self.mode_menu = ctk.CTkOptionMenu(
                btn_row,
                values=mode_options,
                command=self._on_mode_selected,
                width=170,
                height=34,
                fg_color=self.theme.BG_CARD_LIGHT,
                button_color=self.theme.ACCENT_PRIMARY
            )
            self.mode_menu.set(self.controller.current_mode.value)
            self.mode_menu.pack(side="left")
        else:
            self.mode_var = tk.StringVar(value=self.controller.current_mode.value)
            self.mode_menu = ttk.Combobox(
                btn_row,
                textvariable=self.mode_var,
                values=mode_options,
                state="readonly",
                width=20
            )
            self.mode_menu.bind("<<ComboboxSelected>>", lambda e: self._on_mode_selected(self.mode_var.get()))
            self.mode_menu.pack(side="left")

        # ----------------- RIGHT COLUMN: DASHBOARD & ACTIVITY LOG -----------------
        right_col = ctk.CTkFrame(main_container, fg_color="transparent", width=420) if CTK_AVAILABLE else tk.Frame(main_container, bg=self.theme.BG_ROOT, width=420)
        right_col.pack(side="right", fill="both", expand=False)
        right_col.pack_propagate(False)

        # 1. Gesture Reference Guide Card
        ref_card = ctk.CTkFrame(right_col, fg_color=self.theme.BG_CARD, corner_radius=12) if CTK_AVAILABLE else tk.Frame(right_col, bg=self.theme.BG_CARD)
        ref_card.pack(fill="x", pady=(0, 10))

        ref_title = ctk.CTkLabel(
            ref_card,
            text="📖 Gesture Reference Guide",
            font=ctk.CTkFont(family=self.theme.FONT_FAMILY, size=13, weight="bold"),
            text_color=self.theme.TEXT_PRIMARY
        ) if CTK_AVAILABLE else tk.Label(
            ref_card,
            text="📖 Gesture Reference Guide",
            font=(self.theme.FONT_FAMILY, 12, "bold"),
            fg=self.theme.TEXT_PRIMARY,
            bg=self.theme.BG_CARD
        )
        ref_title.pack(anchor="w", padx=14, pady=(10, 6))

        # Reference entries
        gestures_info = [
            ("✊ Fist", "Activate / Unpause Controls"),
            ("👉 Swipe Right", "Next Slide (Right Arrow)"),
            ("👈 Swipe Left", "Previous Slide (Left Arrow)"),
            ("🤏 Pinch Out", "Zoom In (Ctrl + Plus)"),
            ("☝️ Pointing Up", "Scroll Up (+180px)"),
            ("👇 Pointing Down", "Scroll Down (-180px)"),
            ("🖐️ Open Palm", "Safe Pause / Stop Controls"),
        ]

        ref_inner = ctk.CTkFrame(ref_card, fg_color="transparent") if CTK_AVAILABLE else tk.Frame(ref_card, bg=self.theme.BG_CARD)
        ref_inner.pack(fill="x", padx=12, pady=(0, 10))

        for gesture_name, action_desc in gestures_info:
            row = ctk.CTkFrame(ref_inner, fg_color="transparent") if CTK_AVAILABLE else tk.Frame(ref_inner, bg=self.theme.BG_CARD)
            row.pack(fill="x", pady=2)

            g_lbl = ctk.CTkLabel(
                row,
                text=gesture_name,
                font=ctk.CTkFont(family=self.theme.FONT_FAMILY, size=11, weight="bold"),
                text_color=self.theme.TEXT_PRIMARY,
                width=120,
                anchor="w"
            ) if CTK_AVAILABLE else tk.Label(
                row,
                text=gesture_name,
                font=(self.theme.FONT_FAMILY, 10, "bold"),
                fg=self.theme.TEXT_PRIMARY,
                bg=self.theme.BG_CARD,
                width=14,
                anchor="w"
            )
            g_lbl.pack(side="left")

            a_lbl = ctk.CTkLabel(
                row,
                text=f"→  {action_desc}",
                font=ctk.CTkFont(family=self.theme.FONT_FAMILY, size=11),
                text_color=self.theme.TEXT_MUTED,
                anchor="w"
            ) if CTK_AVAILABLE else tk.Label(
                row,
                text=f"→  {action_desc}",
                font=(self.theme.FONT_FAMILY, 10),
                fg=self.theme.TEXT_MUTED,
                bg=self.theme.BG_CARD,
                anchor="w"
            )
            a_lbl.pack(side="left", fill="x", expand=True)

        # 2. Live Activity Log Card
        log_card = ctk.CTkFrame(right_col, fg_color=self.theme.BG_CARD, corner_radius=12) if CTK_AVAILABLE else tk.Frame(right_col, bg=self.theme.BG_CARD)
        log_card.pack(fill="both", expand=True, pady=(0, 10))

        log_header = ctk.CTkFrame(log_card, fg_color="transparent") if CTK_AVAILABLE else tk.Frame(log_card, bg=self.theme.BG_CARD)
        log_header.pack(fill="x", padx=14, pady=(10, 6))

        log_title = ctk.CTkLabel(
            log_header,
            text="📝 Activity Log",
            font=ctk.CTkFont(family=self.theme.FONT_FAMILY, size=13, weight="bold"),
            text_color=self.theme.TEXT_PRIMARY
        ) if CTK_AVAILABLE else tk.Label(
            log_header,
            text="📝 Activity Log",
            font=(self.theme.FONT_FAMILY, 12, "bold"),
            fg=self.theme.TEXT_PRIMARY,
            bg=self.theme.BG_CARD
        )
        log_title.pack(side="left")

        btn_clear = ctk.CTkButton(
            log_header,
            text="Clear",
            font=ctk.CTkFont(family=self.theme.FONT_FAMILY, size=10),
            width=50,
            height=22,
            fg_color=self.theme.BG_CARD_LIGHT,
            hover_color=self.theme.BORDER_COLOR,
            command=self._clear_activity_log
        ) if CTK_AVAILABLE else tk.Button(
            log_header,
            text="Clear",
            font=(self.theme.FONT_FAMILY, 9),
            bg=self.theme.BG_CARD_LIGHT,
            fg=self.theme.TEXT_MUTED,
            command=self._clear_activity_log,
            relief="flat"
        )
        btn_clear.pack(side="right")

        # Scrollable Text Widget for Log
        self.log_text = tk.Text(
            log_card,
            bg=self.theme.BG_CANVAS,
            fg=self.theme.TEXT_PRIMARY,
            font=("Consolas", 10),
            wrap="word",
            relief="flat",
            padx=8,
            pady=8,
            highlightthickness=0
        )
        self.log_text.pack(fill="both", expand=True, padx=12, pady=(0, 10))

        # Tag styles for logs
        self.log_text.tag_config("timestamp", foreground=self.theme.TEXT_DIM)
        self.log_text.tag_config("gesture", foreground=self.theme.ACCENT_ACTIVE)
        self.log_text.tag_config("action", foreground=self.theme.SUCCESS)
        self.log_text.tag_config("warning", foreground=self.theme.WARNING)
        self.log_text.tag_config("danger", foreground=self.theme.DANGER)

        # 3. Recognition Statistics Card
        stats_card = ctk.CTkFrame(right_col, fg_color=self.theme.BG_CARD, corner_radius=12) if CTK_AVAILABLE else tk.Frame(right_col, bg=self.theme.BG_CARD)
        stats_card.pack(fill="x", pady=0)

        stats_inner = ctk.CTkFrame(stats_card, fg_color="transparent") if CTK_AVAILABLE else tk.Frame(stats_card, bg=self.theme.BG_CARD)
        stats_inner.pack(fill="x", padx=14, pady=10)

        self.lbl_stats = ctk.CTkLabel(
            stats_inner,
            text="Actions: 0  |  Gestures: 0  |  Uptime: 00:00",
            font=ctk.CTkFont(family=self.theme.FONT_FAMILY, size=11),
            text_color=self.theme.TEXT_MUTED
        ) if CTK_AVAILABLE else tk.Label(
            stats_inner,
            text="Actions: 0  |  Gestures: 0  |  Uptime: 00:00",
            font=(self.theme.FONT_FAMILY, 10),
            fg=self.theme.TEXT_MUTED,
            bg=self.theme.BG_CARD
        )
        self.lbl_stats.pack(anchor="w")

    def _build_footer(self):
        """Constructs privacy badge, permission details, and shortcut hints."""
        if CTK_AVAILABLE:
            footer = ctk.CTkFrame(self.root, fg_color=self.theme.BG_ROOT, height=28)
        else:
            footer = tk.Frame(self.root, bg=self.theme.BG_ROOT, height=28)
        footer.pack(fill="x", side="bottom", padx=16, pady=(0, 6))

        privacy_lbl = ctk.CTkLabel(
            footer,
            text="🔒 100% Local CV Processing — No camera frames are stored, saved, or uploaded.",
            font=ctk.CTkFont(family=self.theme.FONT_FAMILY, size=10),
            text_color=self.theme.TEXT_DIM
        ) if CTK_AVAILABLE else tk.Label(
            footer,
            text="🔒 100% Local CV Processing — No camera frames are stored, saved, or uploaded.",
            font=(self.theme.FONT_FAMILY, 9),
            fg=self.theme.TEXT_DIM,
            bg=self.theme.BG_ROOT
        )
        privacy_lbl.pack(side="left")

        shortcut_lbl = ctk.CTkLabel(
            footer,
            text="Press [Esc] or [Q] to Emergency Stop",
            font=ctk.CTkFont(family=self.theme.FONT_FAMILY, size=10, weight="bold"),
            text_color=self.theme.TEXT_MUTED
        ) if CTK_AVAILABLE else tk.Label(
            footer,
            text="Press [Esc] or [Q] to Emergency Stop",
            font=(self.theme.FONT_FAMILY, 9, "bold"),
            fg=self.theme.TEXT_MUTED,
            bg=self.theme.BG_ROOT
        )
        shortcut_lbl.pack(side="right")

    def _bind_shortcuts(self):
        """Binds safety emergency stop keys."""
        self.root.bind("<Escape>", lambda e: self.trigger_emergency_stop())
        self.root.bind("q", lambda e: self.trigger_emergency_stop())
        self.root.bind("Q", lambda e: self.trigger_emergency_stop())

    def toggle_camera(self):
        """Starts or stops the webcam feed."""
        if self.camera.is_running:
            self.camera.stop()
            with self._frame_lock:
                self._latest_frame_data = None
            self._update_camera_badge(False)
            if CTK_AVAILABLE:
                self.btn_camera.configure(text="▶ Start Camera", fg_color=self.theme.ACCENT_PRIMARY)
            else:
                self.btn_camera.config(text="▶ Start Camera", bg=self.theme.ACCENT_PRIMARY)
            self.video_label.configure(image="")
            self.video_label.configure(text="Webcam feed paused.\nClick 'Start Camera' to resume tracking.")
            self._log_message("Camera", "Webcam acquisition stopped.", "warning")
        else:
            self._log_message("Camera", "Connecting to webcam device...", "timestamp")
            success = self.camera.start()
            if success:
                self._update_camera_badge(True)
                if CTK_AVAILABLE:
                    self.btn_camera.configure(text="⏹ Stop Camera", fg_color=self.theme.BG_CARD_LIGHT)
                else:
                    self.btn_camera.config(text="⏹ Stop Camera", bg=self.theme.BG_CARD_LIGHT)
                self._log_message("Camera", f"Camera active on device #{self.camera.active_index}.", "action")
            else:
                self._update_camera_badge(False, error=True)
                self._log_message("Camera Error", self.camera.error_message, "danger")
                messagebox.showerror("Camera Connection Failed", self.camera.error_message)

    def toggle_controls(self):
        """Enables or disables computer input actions."""
        if self.controller.is_enabled:
            self.controller.disable_control()
            self._update_control_badge(False)
            if CTK_AVAILABLE:
                self.btn_controls.configure(text="🛡️ Enable Controls", fg_color=self.theme.SUCCESS)
            else:
                self.btn_controls.config(text="🛡️ Enable Controls", bg=self.theme.SUCCESS)
        else:
            self.controller.enable_control()
            self._update_control_badge(True)
            if CTK_AVAILABLE:
                self.btn_controls.configure(text="⏸️ Disable Controls", fg_color=self.theme.WARNING)
            else:
                self.btn_controls.config(text="⏸️ Disable Controls", bg=self.theme.WARNING)

    def trigger_emergency_stop(self):
        """Immediate killswitch execution."""
        self.controller.emergency_stop()
        self._update_control_badge(False, emergency=True)
        if CTK_AVAILABLE:
            self.btn_controls.configure(text="🛡️ Enable Controls", fg_color=self.theme.SUCCESS)
        else:
            self.btn_controls.config(text="🛡️ Enable Controls", bg=self.theme.SUCCESS)
        self._log_message("EMERGENCY", "Immediate Emergency Stop executed. Controls disabled.", "danger")

    def _on_mode_selected(self, mode_str: str):
        """Handles user mode selection."""
        for mode in ControlMode:
            if mode.value == mode_str:
                self.controller.set_mode(mode)
                self._log_message("Mode", f"Active mode set to {mode.value}.", "gesture")
                break

    def _update_camera_badge(self, is_active: bool, error: bool = False):
        if error:
            text = "● CAMERA: ERROR"
            color = self.theme.DANGER
            bg_color = self.theme.DANGER_BG
        elif is_active:
            text = f"● CAMERA: ACTIVE (#{self.camera.active_index})"
            color = self.theme.SUCCESS
            bg_color = self.theme.SUCCESS_BG
        else:
            text = "● CAMERA: OFF"
            color = self.theme.TEXT_MUTED
            bg_color = self.theme.BG_CARD_LIGHT

        if CTK_AVAILABLE:
            self.camera_badge.configure(text=text, text_color=color, fg_color=bg_color)
        else:
            self.camera_badge.config(text=text, fg=color, bg=bg_color)

    def _update_control_badge(self, is_armed: bool, emergency: bool = False):
        if emergency:
            text = "🛑 CONTROLS: EMERGENCY STOPPED"
            color = self.theme.DANGER
            bg_color = self.theme.DANGER_BG
        elif is_armed:
            text = "⚡ CONTROLS: ARMED & ACTIVE"
            color = self.theme.SUCCESS
            bg_color = self.theme.SUCCESS_BG
        else:
            text = "🔒 CONTROLS: DISABLED (SAFE)"
            color = self.theme.WARNING
            bg_color = self.theme.WARNING_BG

        if CTK_AVAILABLE:
            self.control_badge.configure(text=text, text_color=color, fg_color=bg_color)
        else:
            self.control_badge.config(text=text, fg=color, bg=bg_color)

    def _log_message(self, sender: str, msg: str, tag: str = "timestamp"):
        """Appends a line to the Activity Log widget."""
        ts = time.strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{ts}] ", "timestamp")
        self.log_text.insert(tk.END, f"{sender}: ", "gesture" if tag == "gesture" else "timestamp")
        self.log_text.insert(tk.END, f"{msg}\n", tag)
        self.log_text.see(tk.END)

    def _on_action_executed(self, entry: ActionLogEntry):
        """Callback triggered whenever GestureController executes an action."""
        tag = "action"
        if entry.status == "HALTED":
            tag = "danger"
        elif entry.status == "Paused":
            tag = "warning"
        self._log_message(entry.gesture, f"{entry.action} [{entry.status}]", tag)

    def _clear_activity_log(self):
        self.log_text.delete("1.0", tk.END)
        self._log_message("System", "Activity log cleared.")

    def run(self):
        """Starts the frame update loop and Tkinter main loop."""
        self._ui_render_loop()
        self.root.mainloop()

    def _capture_and_perception_worker(self):
        """
        Dedicated background worker thread for camera capture and CV processing.
        Prevents blocking camera I/O and MediaPipe inference on the GUI thread.
        """
        while self._is_active:
            if not self.camera.is_running:
                time.sleep(0.04)
                continue

            ret, frame = self.camera.read_frame()
            if not ret or frame is None:
                time.sleep(0.01)
                continue

            self.total_frames_processed += 1

            # 1. Process hands via MediaPipe
            hands = self.tracker.process(frame)

            # 2. Draw annotations on video
            annotated = self.tracker.draw_annotations(frame, hands)

            # 3. Recognize gestures
            gesture_result: GestureResult = self.recognizer.recognize(hands)

            if gesture_result.gesture != GestureType.NONE:
                self.total_gestures_detected += 1

            # 4. Dispatch to computer controller
            self.controller.process_gesture(gesture_result)

            # 5. Thread-safe store for UI renderer
            with self._frame_lock:
                self._latest_frame_data = (annotated, hands, gesture_result)

    def _ui_render_loop(self):
        """
        UI thread render loop:
        Fetches the latest processed frame from the worker thread,
        renders the canvas preview, and updates telemetry widgets.
        Completely non-blocking.
        """
        if not self._is_active:
            return

        latest = None
        with self._frame_lock:
            latest = self._latest_frame_data

        if latest is not None and self.camera.is_running:
            annotated, hands, gesture_result = latest

            # 1. Update HUD Overlay
            g_name = gesture_result.gesture.value
            conf_pct = int(gesture_result.confidence * 100)
            hud_text = f"Detected: {g_name} ({conf_pct}%)"
            if gesture_result.cooldown_remaining > 0:
                hud_text += f" [Cooldown: {gesture_result.cooldown_remaining}s]"

            if CTK_AVAILABLE:
                self.hud_gesture_lbl.configure(text=hud_text)
                self.hud_telemetry_lbl.configure(
                    text=f"FPS: {self.camera.current_fps:.1f}  |  Hands: {len(hands)}"
                )
            else:
                self.hud_gesture_lbl.config(text=hud_text)
                self.hud_telemetry_lbl.config(
                    text=f"FPS: {self.camera.current_fps:.1f}  |  Hands: {len(hands)}"
                )

            # 2. Render frame to Tkinter Canvas
            view_w = max(320, self.video_label.winfo_width())
            view_h = max(240, self.video_label.winfo_height())
            resized = cv2.resize(annotated, (view_w, view_h), interpolation=cv2.INTER_LINEAR)
            rgb_img = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
            pil_img = Image.fromarray(rgb_img)
            tk_img = ImageTk.PhotoImage(image=pil_img)

            self.video_label.configure(image=tk_img)
            self.video_label.image = tk_img  # Retain reference

        # Update Session Uptime & Statistics
        uptime_sec = int(time.time() - self.session_start_time)
        mins, secs = divmod(uptime_sec, 60)
        stats_str = (
            f"Actions: {self.controller.total_actions_executed}  |  "
            f"Gestures: {self.total_gestures_detected}  |  "
            f"Uptime: {mins:02d}:{secs:02d}"
        )
        if CTK_AVAILABLE:
            self.lbl_stats.configure(text=stats_str)
        else:
            self.lbl_stats.config(text=stats_str)

        # Schedule next loop iteration
        if self._is_active:
            self.root.after(self._loop_delay_ms, self._ui_render_loop)

    def on_close(self):
        """Clean resource release upon closing application."""
        self._is_active = False
        self.camera.stop()
        self.tracker.close()
        self.root.destroy()
