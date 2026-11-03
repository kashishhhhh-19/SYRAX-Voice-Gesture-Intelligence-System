"""
gui/dashboard.py - Futuristic Control Room Dashboard for SYRAX
Central UI hosting AI Waveform, Voice Controls, Gesture Tracking Preview,
System Status Monitoring, and Live Timestamped Activity History.
All cross-thread updates are safely marshaled via queue.Queue and root.after().
"""

import datetime
import queue
import threading
import time
import tkinter as tk
from tkinter import ttk
from typing import Any, Dict, List, Optional

import config
from core.assistant_engine import AssistantEngine
from core.event_bus import Events, get_event_bus
from core.logger import get_logger
from gui.widgets import CameraPreviewWidget, NeonButton, NeonCard, StatusPill, WaveformVisualizer

logger = get_logger("Dashboard")


class Dashboard:
    """
    Futuristic sci-fi desktop dashboard for SYRAX.
    Dark cyberpunk palette with neon cyan and blue accents.
    """

    def __init__(self, root: tk.Tk, assistant_engine: AssistantEngine) -> None:
        self.root = root
        self.engine = assistant_engine
        self._event_bus = get_event_bus()

        # Thread-safe UI update queue
        self._ui_queue: queue.Queue = queue.Queue()

        # System state tracking
        self._internet_connected = False
        self._last_cmd_str = "None"

        # Setup root window
        self._setup_window()

        # Build futuristic interface sections
        self._build_ui()

        # Register event bus listeners
        self._subscribe_events()

        # Start periodic background monitor (Internet ping & UI queue pump)
        self._start_monitors()

    def _setup_window(self) -> None:
        """Configure main window properties, theme, and close handler."""
        self.root.title(f"{config.APP_NAME} - Voice & Gesture Intelligence System")
        self.root.geometry("1180x760")
        self.root.minsize(980, 680)
        self.root.configure(bg=config.COLOR_BG_DARK)

        # Intercept window close for graceful multi-threaded shutdown
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        # Style TTK Combobox to match dark theme
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "Dark.TCombobox",
            fieldbackground=config.COLOR_BG_INPUT,
            background=config.COLOR_BG_CARD,
            foreground=config.COLOR_TEXT_PRIMARY,
            darkcolor=config.COLOR_BORDER,
            lightcolor=config.COLOR_BORDER,
            arrowcolor=config.COLOR_CYAN_NEON
        )

    def _build_ui(self) -> None:
        """Construct the 5 dashboard sections inside a responsive layout."""
        # Main Container
        main_frame = tk.Frame(self.root, bg=config.COLOR_BG_DARK)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)

        # ----------------------------------------------------------------------
        # HEADER BAR: Brand Logo, Tagline, Time, Quick Exit
        # ----------------------------------------------------------------------
        header = tk.Frame(main_frame, bg=config.COLOR_BG_DARK)
        header.pack(fill=tk.X, pady=(0, 10))

        # Brand title
        title_box = tk.Frame(header, bg=config.COLOR_BG_DARK)
        title_box.pack(side=tk.LEFT)

        brand_lbl = tk.Label(
            title_box,
            text=config.APP_NAME,
            font=(config.FONT_FAMILY, 20, "bold"),
            fg=config.COLOR_CYAN_NEON,
            bg=config.COLOR_BG_DARK
        )
        brand_lbl.pack(side=tk.LEFT)

        tagline_lbl = tk.Label(
            title_box,
            text=f"  //  {config.TAGLINE}",
            font=(config.FONT_FAMILY, 10, "italic"),
            fg=config.COLOR_TEXT_MUTED,
            bg=config.COLOR_BG_DARK
        )
        tagline_lbl.pack(side=tk.LEFT, pady=(6, 0))

        # Right Header: Clock & Version
        self.clock_lbl = tk.Label(
            header,
            text="--:--:--",
            font=(config.FONT_MONO, 11, "bold"),
            fg=config.COLOR_BLUE_NEON,
            bg=config.COLOR_BG_DARK
        )
        self.clock_lbl.pack(side=tk.RIGHT, padx=6)

        # ----------------------------------------------------------------------
        # SECTION A: CENTRAL AI ASSISTANT (Top Hero Card)
        # ----------------------------------------------------------------------
        self.hero_card = NeonCard(main_frame, title="Central AI Assistant", accent_color=config.COLOR_CYAN_NEON)
        self.hero_card.pack(fill=tk.X, pady=(0, 10))

        hero_body = tk.Frame(self.hero_card, bg=config.COLOR_BG_CARD)
        hero_body.pack(fill=tk.X)

        # Animated Waveform
        self.waveform = WaveformVisualizer(hero_body, height=65)
        self.waveform.pack(fill=tk.X, pady=(0, 8))

        # Assistant Spoken Response Display
        self.response_display = tk.Label(
            hero_body,
            text=config.GREETING_TEXT,
            font=(config.FONT_FAMILY, 12, "bold"),
            fg=config.COLOR_CYAN_NEON,
            bg=config.COLOR_BG_PANEL,
            padx=12,
            pady=8,
            relief=tk.FLAT,
            anchor="w",
            wraplength=1050
        )
        self.response_display.pack(fill=tk.X, pady=(0, 6))

        # Pending Message Confirmation Card (Transient - Hidden until message drafted)
        self.confirmation_frame = tk.Frame(
            hero_body,
            bg=config.COLOR_BG_PANEL,
            highlightthickness=1,
            highlightbackground=config.COLOR_YELLOW_NEON,
            padx=10,
            pady=6
        )
        # Note: Packed dynamically when WHATSAPP_CONFIRMATION_PENDING arrives

        self.lbl_confirm_details = tk.Label(
            self.confirmation_frame,
            text="",
            font=(config.FONT_FAMILY, 9, "bold"),
            fg=config.COLOR_YELLOW_NEON,
            bg=config.COLOR_BG_PANEL,
            anchor="w"
        )
        self.lbl_confirm_details.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.btn_confirm_send = NeonButton(
            self.confirmation_frame,
            text="SEND (Yes)",
            command=self._on_confirm_send,
            accent_color=config.COLOR_GREEN_NEON,
            width=10
        )
        self.btn_confirm_send.pack(side=tk.RIGHT, padx=(6, 0))

        self.btn_confirm_cancel = NeonButton(
            self.confirmation_frame,
            text="CANCEL (No)",
            command=self._on_confirm_cancel,
            accent_color=config.COLOR_RED_NEON,
            width=11
        )
        self.btn_confirm_cancel.pack(side=tk.RIGHT)

        # Command Input Field for Manual Testing
        input_row = tk.Frame(hero_body, bg=config.COLOR_BG_CARD)
        input_row.pack(fill=tk.X)

        input_prefix = tk.Label(
            input_row,
            text="COMMAND >",
            font=(config.FONT_MONO, 10, "bold"),
            fg=config.COLOR_TEXT_MUTED,
            bg=config.COLOR_BG_CARD
        )
        input_prefix.pack(side=tk.LEFT, padx=(0, 6))

        self.cmd_entry = tk.Entry(
            input_row,
            font=(config.FONT_FAMILY, 10),
            bg=config.COLOR_BG_INPUT,
            fg=config.COLOR_TEXT_PRIMARY,
            insertbackground=config.COLOR_CYAN_NEON,
            relief=tk.FLAT,
            highlightthickness=1,
            highlightbackground=config.COLOR_BORDER,
            highlightcolor=config.COLOR_CYAN_NEON
        )
        self.cmd_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8), ipady=3)
        self.cmd_entry.bind("<Return>", lambda e: self._on_submit_text_cmd())

        self.btn_exec = NeonButton(input_row, text="Execute", command=self._on_submit_text_cmd, width=9)
        self.btn_exec.pack(side=tk.LEFT, padx=(0, 6))

        # Universal Emergency Cancel / Stop Operation Button
        self.btn_stop_cancel = NeonButton(
            input_row,
            text="STOP / CANCEL",
            command=self._on_cancel_current_operation,
            accent_color=config.COLOR_RED_NEON,
            width=14
        )
        self.btn_stop_cancel.pack(side=tk.RIGHT)

        # ----------------------------------------------------------------------
        # MIDDLE SPLIT: Left (Voice & Gesture), Right (System & Activity Log)
        # ----------------------------------------------------------------------
        middle_row = tk.Frame(main_frame, bg=config.COLOR_BG_DARK)
        middle_row.pack(fill=tk.BOTH, expand=True)

        left_col = tk.Frame(middle_row, bg=config.COLOR_BG_DARK, width=540)
        left_col.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 6))

        right_col = tk.Frame(middle_row, bg=config.COLOR_BG_DARK, width=540)
        right_col.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(6, 0))

        # ----------------------------------------------------------------------
        # SECTION B: VOICE CONTROL (Left Column Top)
        # ----------------------------------------------------------------------
        voice_card = NeonCard(left_col, title="Voice Intelligence", accent_color=config.COLOR_GREEN_NEON)
        voice_card.pack(fill=tk.X, pady=(0, 10))

        # Row 1: Mic Toggle + Status Pill + Recalibrate
        v_row1 = tk.Frame(voice_card, bg=config.COLOR_BG_CARD)
        v_row1.pack(fill=tk.X, pady=(0, 6))

        self.btn_mic_toggle = NeonButton(
            v_row1,
            text="MIC ON",
            command=self._on_toggle_mic,
            accent_color=config.COLOR_GREEN_NEON,
            width=11
        )
        self.btn_mic_toggle.pack(side=tk.LEFT, padx=(0, 8))

        self.pill_voice_status = StatusPill(v_row1, text="LISTENING")
        self.pill_voice_status.pack(side=tk.LEFT, padx=(0, 8))

        self.btn_recalibrate = NeonButton(
            v_row1,
            text="Calibrate Noise",
            command=self._on_recalibrate_noise,
            accent_color=config.COLOR_YELLOW_NEON,
            width=14
        )
        self.btn_recalibrate.pack(side=tk.RIGHT)

        # Row 2: Recognized Speech Text
        v_row2 = tk.Frame(voice_card, bg=config.COLOR_BG_CARD)
        v_row2.pack(fill=tk.X, pady=(2, 6))

        tk.Label(
            v_row2,
            text="Last Heard:",
            font=(config.FONT_FAMILY, 9),
            fg=config.COLOR_TEXT_MUTED,
            bg=config.COLOR_BG_CARD
        ).pack(side=tk.LEFT)

        self.lbl_recognized = tk.Label(
            v_row2,
            text='"(Waiting for voice command...)"',
            font=(config.FONT_FAMILY, 9, "italic"),
            fg=config.COLOR_TEXT_PRIMARY,
            bg=config.COLOR_BG_CARD,
            anchor="w"
        )
        self.lbl_recognized.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(6, 0))

        # Row 3: Device Selection Dropdown
        v_row3 = tk.Frame(voice_card, bg=config.COLOR_BG_CARD)
        v_row3.pack(fill=tk.X)

        tk.Label(
            v_row3,
            text="Input Mic:",
            font=(config.FONT_FAMILY, 9),
            fg=config.COLOR_TEXT_MUTED,
            bg=config.COLOR_BG_CARD
        ).pack(side=tk.LEFT, padx=(0, 6))

        self.combo_devices = ttk.Combobox(
            v_row3,
            style="Dark.TCombobox",
            state="readonly",
            font=(config.FONT_FAMILY, 8)
        )
        self.combo_devices.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.combo_devices.bind("<<ComboboxSelected>>", self._on_device_selected)

        # ----------------------------------------------------------------------
        # SECTION C: GESTURE CONTROL (Left Column Bottom)
        # ----------------------------------------------------------------------
        gesture_card = NeonCard(left_col, title="Gesture Intelligence (GestureFlow)", accent_color=config.COLOR_PURPLE_NEON)
        gesture_card.pack(fill=tk.BOTH, expand=True)

        # Row 1: Camera Toggle & Mode Pills
        g_row1 = tk.Frame(gesture_card, bg=config.COLOR_BG_CARD)
        g_row1.pack(fill=tk.X, pady=(0, 6))

        self.btn_cam_toggle = NeonButton(
            g_row1,
            text="CAMERA ON",
            command=self._on_toggle_camera,
            accent_color=config.COLOR_PURPLE_NEON,
            width=12
        )
        self.btn_cam_toggle.pack(side=tk.LEFT, padx=(0, 8))

        tk.Label(
            g_row1,
            text="Hand:",
            font=(config.FONT_FAMILY, 9),
            fg=config.COLOR_TEXT_MUTED,
            bg=config.COLOR_BG_CARD
        ).pack(side=tk.LEFT, padx=(0, 4))

        self.pill_hand = StatusPill(g_row1, text="NO")
        self.pill_hand.pack(side=tk.LEFT, padx=(0, 10))

        tk.Label(
            g_row1,
            text="Mode:",
            font=(config.FONT_FAMILY, 9),
            fg=config.COLOR_TEXT_MUTED,
            bg=config.COLOR_BG_CARD
        ).pack(side=tk.LEFT, padx=(0, 4))

        self.pill_gesture_mode = StatusPill(g_row1, text="IDLE")
        self.pill_gesture_mode.pack(side=tk.LEFT, padx=(0, 8))

        self.btn_gesture_voice = NeonButton(
            g_row1,
            text="VOICE: ON",
            command=self._on_toggle_gesture_voice,
            accent_color=config.COLOR_CYAN_NEON,
            width=10
        )
        self.btn_gesture_voice.pack(side=tk.RIGHT)

        # Row 2: Gesture status and Camera Preview
        g_body = tk.Frame(gesture_card, bg=config.COLOR_BG_CARD)
        g_body.pack(fill=tk.BOTH, expand=True)

        # Video Preview Canvas
        self.cam_preview = CameraPreviewWidget(g_body, width=220, height=140)
        self.cam_preview.pack(side=tk.LEFT, padx=(0, 10))

        # Gesture Info Pane
        g_info = tk.Frame(g_body, bg=config.COLOR_BG_CARD)
        g_info.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        tk.Label(
            g_info,
            text="Current Gesture:",
            font=(config.FONT_FAMILY, 9),
            fg=config.COLOR_TEXT_MUTED,
            bg=config.COLOR_BG_CARD
        ).pack(anchor="w")

        self.lbl_current_gesture = tk.Label(
            g_info,
            text="--",
            font=(config.FONT_MONO, 12, "bold"),
            fg=config.COLOR_CYAN_NEON,
            bg=config.COLOR_BG_CARD
        )
        self.lbl_current_gesture.pack(anchor="w", pady=(2, 6))

        gesture_guide = (
            "YouTube Controls:\n"
            "* Fist (~1s) -> Toggle Mode\n"
            "* Steady Palm (0.5s) -> Play/Pause\n"
            "* Swipe R/L -> Next/Prev Video\n"
            "* 2-Finger R/L -> Fwd/Rewind\n"
            "* 1-Finger Up/Dn -> Scroll\n"
            "* Pinch Out/In -> Zoom In/Out"
        )
        tk.Label(
            g_info,
            text=gesture_guide,
            font=(config.FONT_MONO, 8),
            fg=config.COLOR_TEXT_DIM,
            bg=config.COLOR_BG_CARD,
            justify=tk.LEFT
        ).pack(anchor="w")

        # ----------------------------------------------------------------------
        # SECTION D: SYSTEM STATUS (Right Column Top)
        # ----------------------------------------------------------------------
        status_card = NeonCard(right_col, title="System Status & Telemetry", accent_color=config.COLOR_BLUE_NEON)
        status_card.pack(fill=tk.X, pady=(0, 10))

        # Status Grid
        grid_frame = tk.Frame(status_card, bg=config.COLOR_BG_CARD)
        grid_frame.pack(fill=tk.X)

        # Voice Backend Status
        tk.Label(grid_frame, text="Voice Engine:", font=(config.FONT_FAMILY, 9), fg=config.COLOR_TEXT_MUTED, bg=config.COLOR_BG_CARD).grid(row=0, column=0, sticky="w", pady=2)
        self.pill_voice_backend = StatusPill(grid_frame, text="ACTIVE")
        self.pill_voice_backend.grid(row=0, column=1, sticky="w", padx=6, pady=2)

        # Camera Status
        tk.Label(grid_frame, text="Vision Tracker:", font=(config.FONT_FAMILY, 9), fg=config.COLOR_TEXT_MUTED, bg=config.COLOR_BG_CARD).grid(row=0, column=2, sticky="w", padx=(12, 0), pady=2)
        self.pill_cam_status = StatusPill(grid_frame, text="ACTIVE")
        self.pill_cam_status.grid(row=0, column=3, sticky="w", padx=6, pady=2)

        # Internet Status
        tk.Label(grid_frame, text="Internet (STT):", font=(config.FONT_FAMILY, 9), fg=config.COLOR_TEXT_MUTED, bg=config.COLOR_BG_CARD).grid(row=1, column=0, sticky="w", pady=2)
        self.pill_internet = StatusPill(grid_frame, text="CONNECTING")
        self.pill_internet.grid(row=1, column=1, sticky="w", padx=6, pady=2)

        # Last Command
        tk.Label(grid_frame, text="Last Command:", font=(config.FONT_FAMILY, 9), fg=config.COLOR_TEXT_MUTED, bg=config.COLOR_BG_CARD).grid(row=1, column=2, sticky="w", padx=(12, 0), pady=2)
        self.lbl_last_cmd = tk.Label(
            grid_frame,
            text="None",
            font=(config.FONT_MONO, 9, "bold"),
            fg=config.COLOR_CYAN_NEON,
            bg=config.COLOR_BG_CARD
        )
        self.lbl_last_cmd.grid(row=1, column=3, sticky="w", padx=6, pady=2)

        # YouTube Browser Focus Status
        tk.Label(grid_frame, text="YouTube Focus:", font=(config.FONT_FAMILY, 9), fg=config.COLOR_TEXT_MUTED, bg=config.COLOR_BG_CARD).grid(row=2, column=0, sticky="w", pady=2)
        self.pill_youtube_focus = StatusPill(grid_frame, text="YouTube Not Found")
        self.pill_youtube_focus.grid(row=2, column=1, columnspan=3, sticky="w", padx=6, pady=2)

        # Active App Context & Intent Readout
        tk.Label(grid_frame, text="Active App:", font=(config.FONT_FAMILY, 9), fg=config.COLOR_TEXT_MUTED, bg=config.COLOR_BG_CARD).grid(row=3, column=0, sticky="w", pady=2)
        self.pill_active_app = StatusPill(grid_frame, text="GENERAL")
        self.pill_active_app.grid(row=3, column=1, sticky="w", padx=6, pady=2)

        tk.Label(grid_frame, text="Intent / Mode:", font=(config.FONT_FAMILY, 9), fg=config.COLOR_TEXT_MUTED, bg=config.COLOR_BG_CARD).grid(row=3, column=2, sticky="w", padx=(12, 0), pady=2)
        self.lbl_intent = tk.Label(
            grid_frame,
            text="None",
            font=(config.FONT_MONO, 9, "bold"),
            fg=config.COLOR_CYAN_NEON,
            bg=config.COLOR_BG_CARD
        )
        self.lbl_intent.grid(row=3, column=3, sticky="w", padx=6, pady=2)

        # Social & Messaging Telemetry
        tk.Label(grid_frame, text="WhatsApp:", font=(config.FONT_FAMILY, 9), fg=config.COLOR_TEXT_MUTED, bg=config.COLOR_BG_CARD).grid(row=4, column=0, sticky="w", pady=2)
        self.pill_whatsapp_status = StatusPill(grid_frame, text="IDLE")
        self.pill_whatsapp_status.grid(row=4, column=1, sticky="w", padx=6, pady=2)

        tk.Label(grid_frame, text="Instagram:", font=(config.FONT_FAMILY, 9), fg=config.COLOR_TEXT_MUTED, bg=config.COLOR_BG_CARD).grid(row=4, column=2, sticky="w", padx=(12, 0), pady=2)
        self.pill_instagram_status = StatusPill(grid_frame, text="IDLE")
        self.pill_instagram_status.grid(row=4, column=3, sticky="w", padx=6, pady=2)

        # Browser CDP Connection Status
        tk.Label(grid_frame, text="Browser CDP:", font=(config.FONT_FAMILY, 9), fg=config.COLOR_TEXT_MUTED, bg=config.COLOR_BG_CARD).grid(row=5, column=0, sticky="w", pady=2)
        self.pill_browser_cdp = StatusPill(grid_frame, text="DISCONNECTED")
        self.pill_browser_cdp.grid(row=5, column=1, sticky="w", padx=6, pady=2)

        # Diagnostics Run Button
        diag_row = tk.Frame(status_card, bg=config.COLOR_BG_CARD)
        diag_row.pack(fill=tk.X, pady=(8, 0))

        self.btn_diagnostics = NeonButton(
            diag_row,
            text="RUN DIAGNOSTICS",
            command=self._on_run_diagnostics,
            accent_color=config.COLOR_CYAN_NEON,
            width=18
        )
        self.btn_diagnostics.pack(side=tk.LEFT)

        tk.Label(
            diag_row,
            text="Self-tests Mic, STT, SAPI TTS, Camera, and PyAutoGUI.",
            font=(config.FONT_FAMILY, 8),
            fg=config.COLOR_TEXT_DIM,
            bg=config.COLOR_BG_CARD
        ).pack(side=tk.LEFT, padx=(10, 0))

        # ----------------------------------------------------------------------
        # SECTION E: ACTIVITY HISTORY (Right Column Bottom)
        # ----------------------------------------------------------------------
        history_card = NeonCard(right_col, title="Activity History & Command Logs", accent_color=config.COLOR_YELLOW_NEON)
        history_card.pack(fill=tk.BOTH, expand=True)

        # Header controls
        h_ctrl = tk.Frame(history_card, bg=config.COLOR_BG_CARD)
        h_ctrl.pack(fill=tk.X, pady=(0, 6))

        tk.Label(
            h_ctrl,
            text="Real-time Event Stream:",
            font=(config.FONT_FAMILY, 8),
            fg=config.COLOR_TEXT_MUTED,
            bg=config.COLOR_BG_CARD
        ).pack(side=tk.LEFT)

        btn_clear = NeonButton(
            h_ctrl,
            text="Clear",
            command=self._on_clear_history,
            accent_color=config.COLOR_TEXT_MUTED,
            width=7
        )
        btn_clear.pack(side=tk.RIGHT)

        # Scrollable Text Container
        text_frame = tk.Frame(history_card, bg=config.COLOR_BG_CARD)
        text_frame.pack(fill=tk.BOTH, expand=True)

        scrollbar = tk.Scrollbar(text_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.history_text = tk.Text(
            text_frame,
            bg=config.COLOR_BG_INPUT,
            fg=config.COLOR_TEXT_PRIMARY,
            font=(config.FONT_MONO, 9),
            relief=tk.FLAT,
            yscrollcommand=scrollbar.set,
            wrap=tk.WORD,
            highlightthickness=1,
            highlightbackground=config.COLOR_BORDER
        )
        self.history_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.history_text.yview)

        # Configure color tags for log categories
        self.history_text.tag_configure("TIME", foreground=config.COLOR_TEXT_DIM)
        self.history_text.tag_configure("VOICE", foreground=config.COLOR_CYAN_NEON)
        self.history_text.tag_configure("GESTURE", foreground=config.COLOR_PURPLE_NEON)
        self.history_text.tag_configure("ACTION", foreground=config.COLOR_GREEN_NEON)
        self.history_text.tag_configure("SYSTEM", foreground=config.COLOR_BLUE_NEON)
        self.history_text.tag_configure("FOCUS", foreground=config.COLOR_YELLOW_NEON)
        self.history_text.tag_configure("ERROR", foreground=config.COLOR_RED_NEON)
        self.history_text.tag_configure("DIAG", foreground=config.COLOR_YELLOW_NEON)

        # Populate audio devices and initialize status indicators after ALL widgets are constructed
        self._populate_audio_devices()

    def _subscribe_events(self) -> None:
        """Register thread-safe listeners to EventBus events."""
        bus = self._event_bus
        bus.subscribe(Events.VOICE_STATUS_CHANGED, lambda **kw: self._ui_queue.put(("VOICE_STATUS", kw)))
        bus.subscribe(Events.VOICE_RECOGNIZED, lambda **kw: self._ui_queue.put(("VOICE_RECOGNIZED", kw)))
        bus.subscribe(Events.VOICE_SPEECH_START, lambda **kw: self._ui_queue.put(("SPEECH_START", kw)))
        bus.subscribe(Events.VOICE_SPEECH_END, lambda **kw: self._ui_queue.put(("SPEECH_END", kw)))
        bus.subscribe(Events.VOICE_ERROR, lambda **kw: self._ui_queue.put(("VOICE_ERROR", kw)))

        bus.subscribe(Events.GESTURE_STATUS_CHANGED, lambda **kw: self._ui_queue.put(("GESTURE_STATUS", kw)))
        bus.subscribe(Events.GESTURE_FRAME, lambda **kw: self._ui_queue.put(("GESTURE_FRAME", kw)))
        bus.subscribe(Events.GESTURE_DETECTED, lambda **kw: self._ui_queue.put(("GESTURE_DETECTED", kw)))
        bus.subscribe(Events.GESTURE_MODE_TOGGLED, lambda **kw: self._ui_queue.put(("GESTURE_MODE_TOGGLED", kw)))
        bus.subscribe(Events.YOUTUBE_FOCUS_CHANGED, lambda **kw: self._ui_queue.put(("YOUTUBE_FOCUS", kw)))
        bus.subscribe(Events.ACTIVE_APP_CHANGED, lambda **kw: self._ui_queue.put(("ACTIVE_APP_CHANGED", kw)))

        bus.subscribe(Events.WHATSAPP_CONFIRMATION_PENDING, lambda **kw: self._ui_queue.put(("WHATSAPP_CONFIRMATION_PENDING", kw)))
        bus.subscribe(Events.WHATSAPP_MESSAGE_SENT, lambda **kw: self._ui_queue.put(("WHATSAPP_MESSAGE_SENT", kw)))
        bus.subscribe(Events.WHATSAPP_MESSAGE_CANCELLED, lambda **kw: self._ui_queue.put(("WHATSAPP_MESSAGE_CANCELLED", kw)))
        bus.subscribe(Events.INSTAGRAM_STATUS_CHANGED, lambda **kw: self._ui_queue.put(("INSTAGRAM_STATUS", kw)))

        bus.subscribe(Events.ACTION_EXECUTED, lambda **kw: self._ui_queue.put(("ACTION_EXECUTED", kw)))
        bus.subscribe(Events.ASSISTANT_RESPONSE, lambda **kw: self._ui_queue.put(("ASSISTANT_RESPONSE", kw)))
        bus.subscribe(Events.ACTIVITY_LOG, lambda **kw: self._ui_queue.put(("ACTIVITY_LOG", kw)))
        bus.subscribe(Events.DIAGNOSTIC_RESULT, lambda **kw: self._ui_queue.put(("DIAGNOSTIC_RESULT", kw)))
        bus.subscribe(Events.SHUTDOWN_REQUESTED, lambda **kw: self._ui_queue.put(("SHUTDOWN", kw)))

    def _start_monitors(self) -> None:
        """Start UI polling and periodic background connectivity checks."""
        # Process UI queue every 25ms
        self._process_ui_queue()

        # Update clock every 1 second
        self._update_clock()

        # Background thread for periodic internet checking
        threading.Thread(target=self._internet_check_loop, name="SYRAX-NetCheck", daemon=True).start()

    def _process_ui_queue(self) -> None:
        """Consume all pending UI update tasks from background threads."""
        while not self._ui_queue.empty():
            try:
                event_type, data = self._ui_queue.get_nowait()
                self._handle_ui_event(event_type, data)
            except queue.Empty:
                break
            except Exception as exc:
                logger.error(f"Error handling UI event: {exc}", exc_info=True)

        self.root.after(25, self._process_ui_queue)

    def _handle_ui_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """Apply received event data directly to Tkinter widgets."""
        if event_type == "VOICE_STATUS":
            status = data.get("status", "IDLE")
            self.pill_voice_status.set_state(status)
            self.waveform.set_state(status)

        elif event_type == "VOICE_RECOGNIZED":
            text = data.get("text", "")
            self.lbl_recognized.config(text=f'"{text}"')
            self.lbl_last_cmd.config(text=text[:25])

        elif event_type == "SPEECH_START":
            self.waveform.set_state("SPEAKING")

        elif event_type == "SPEECH_END":
            # Return to listening or idle
            mic_on = self.engine.voice_engine.is_mic_enabled()
            self.waveform.set_state("LISTENING" if mic_on else "OFF")

        elif event_type == "VOICE_ERROR":
            err_msg = data.get("message", "Microphone Error")
            self.pill_voice_status.set_state("ERROR")
            self.log_activity("ERROR", f"Voice Subsystem: {err_msg}")

        elif event_type == "GESTURE_STATUS":
            status = data.get("status", "IDLE")
            self.pill_gesture_mode.set_state(status)
            cam_active = self.engine.gesture_engine.is_camera_enabled()
            self.pill_cam_status.set_state("ACTIVE" if cam_active else "OFF")

        elif event_type == "GESTURE_FRAME":
            frame = data.get("frame")
            hand_detected = data.get("hand_detected", False)
            gesture = data.get("gesture", "NONE")
            confidence = data.get("confidence", 0.0)
            state = data.get("state", "IDLE")

            if frame is not None:
                self.cam_preview.update_frame(frame)
            self.pill_hand.set_state("YES" if hand_detected else "NO")
            self.pill_gesture_mode.set_state(state)
            if gesture not in ("NONE", "UNKNOWN"):
                self.lbl_current_gesture.config(text=f"{gesture} ({int(confidence * 100)}%)")

        elif event_type == "GESTURE_DETECTED":
            gesture = data.get("gesture", "")
            desc = data.get("description", "")
            confidence = data.get("confidence", 1.0)
            conf_str = f" ({int(confidence * 100)}%)" if confidence < 1.0 else ""
            self.lbl_current_gesture.config(text=f"{gesture}{conf_str}")
            self.lbl_last_cmd.config(text=f"Gesture: {gesture}")

        elif event_type == "GESTURE_MODE_TOGGLED":
            state = data.get("state", "IDLE")
            self.pill_gesture_mode.set_state(state)
            self.log_activity("GESTURE", f"Gesture Mode Toggled: {state}")

        elif event_type == "YOUTUBE_FOCUS":
            status = data.get("status", "YouTube Not Found")
            self.pill_youtube_focus.set_state(status)
            msg = data.get("message", "")
            if msg:
                self.log_activity("FOCUS", msg)

        elif event_type == "NET_STATUS":
            connected = data.get("connected", False)
            if hasattr(self, "pill_internet"):
                self.pill_internet.set_state("CONNECTED" if connected else "DISCONNECTED")

        elif event_type == "BROWSER_CDP_STATUS":
            connected = data.get("connected", False)
            if hasattr(self, "pill_browser_cdp"):
                self.pill_browser_cdp.set_state("CONNECTED" if connected else "DISCONNECTED")

        elif event_type == "ACTIVE_APP_CHANGED":
            app = data.get("app", "general").upper()
            if hasattr(self, "pill_active_app"):
                self.pill_active_app.set_state(app)
            self.log_activity("SYSTEM", f"Active App Foreground: {app}")

        elif event_type == "WHATSAPP_CONFIRMATION_PENDING":
            recipient = data.get("recipient", "Contact")
            content = data.get("content", "")
            if hasattr(self, "confirmation_frame"):
                self.lbl_confirm_details.config(
                    text=f"CONFIRM SEND TO {recipient.upper()}?  \"{content}\""
                )
                self.confirmation_frame.pack(fill=tk.X, pady=(0, 6), before=self.cmd_entry.master)
            if hasattr(self, "pill_whatsapp_status"):
                self.pill_whatsapp_status.set_state("CONFIRMATION")

        elif event_type == "WHATSAPP_MESSAGE_SENT":
            recipient = data.get("recipient", "Contact")
            if hasattr(self, "confirmation_frame"):
                self.confirmation_frame.pack_forget()
            if hasattr(self, "pill_whatsapp_status"):
                self.pill_whatsapp_status.set_state("SENT")
            self.log_activity("MESSAGING", f"WhatsApp message sent to {recipient}")

        elif event_type == "WHATSAPP_MESSAGE_CANCELLED":
            if hasattr(self, "confirmation_frame"):
                self.confirmation_frame.pack_forget()
            if hasattr(self, "pill_whatsapp_status"):
                self.pill_whatsapp_status.set_state("CANCELLED")
            self.log_activity("MESSAGING", "WhatsApp message cancelled")

        elif event_type == "INSTAGRAM_STATUS":
            status = data.get("status", "IDLE")
            if hasattr(self, "pill_instagram_status"):
                self.pill_instagram_status.set_state(status)

        elif event_type == "ACTION_EXECUTED":
            cmd = data.get("command", "")
            spoken = data.get("spoken", "")
            intent = data.get("intent", "")
            if hasattr(self, "lbl_intent") and intent:
                self.lbl_intent.config(text=intent.upper()[:20])
            self.lbl_last_cmd.config(text=cmd[:25])
            self.log_activity("ACTION", f"Executed: '{cmd}' -> {spoken}")

        elif event_type == "ASSISTANT_RESPONSE":
            resp = data.get("text", "")
            self.response_display.config(text=resp)

        elif event_type == "ACTIVITY_LOG":
            cat = data.get("category", "SYSTEM")
            msg = data.get("message", "")
            self.log_activity(cat, msg)

        elif event_type == "DIAGNOSTIC_RESULT":
            sub = data.get("subsystem", "")
            passed = data.get("passed", False)
            msg = data.get("message", "")
            hint = data.get("fix_hint", "")
            status_tag = "PASS" if passed else "FAIL"
            self.log_activity("DIAG", f"[{status_tag}] {sub}: {msg}")
            if not passed and hint:
                self.log_activity("ERROR", f"Fix Hint: {hint}")

        elif event_type == "SHUTDOWN":
            self.on_close()

    def log_activity(self, category: str, message: str) -> None:
        """Append formatted timestamped line into activity history."""
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        self.history_text.insert(tk.END, f"[{timestamp}] ", "TIME")
        cat_tag = category.upper() if category.upper() in (
            "VOICE", "GESTURE", "ACTION", "SYSTEM", "ERROR", "DIAG"
        ) else "SYSTEM"
        self.history_text.insert(tk.END, f"[{cat_tag}] ", cat_tag)
        self.history_text.insert(tk.END, f"{message}\n")
        self.history_text.see(tk.END)

    def _update_clock(self) -> None:
        """Update live digital clock in header."""
        now_str = datetime.datetime.now().strftime("%Y-%m-%d  %H:%M:%S")
        self.clock_lbl.config(text=now_str)
        self.root.after(1000, self._update_clock)

    def _internet_check_loop(self) -> None:
        """Periodically ping internet connectivity."""
        import urllib.request
        while True:
            try:
                urllib.request.urlopen("https://www.google.com", timeout=3.0)
                connected = True
            except Exception:
                connected = False

            if connected != self._internet_connected:
                self._internet_connected = connected
                self._ui_queue.put((
                    "ACTIVITY_LOG",
                    {"category": "SYSTEM", "message": f"Network Connectivity: {'ONLINE' if connected else 'OFFLINE'}"}
                ))

            self._ui_queue.put(("NET_STATUS", {"connected": connected}))

            # Check CDP status
            try:
                from core.browser_manager import get_browser_manager
                bm = get_browser_manager()
                self._ui_queue.put(("BROWSER_CDP_STATUS", {"connected": bm.is_connected()}))
            except Exception:
                pass

            time.sleep(10.0)

    def _populate_audio_devices(self) -> None:
        """Populate combobox with physical input devices and update voice backend status pill."""
        try:
            devices = self.engine.voice_engine.get_available_devices()
            names = [f"[{d['index']}] {d['name']}" for d in devices]
            if hasattr(self, "combo_devices"):
                self.combo_devices["values"] = names

                current_name = self.engine.voice_engine.get_current_device_name()
                matched = False
                for idx, n in enumerate(names):
                    if current_name and current_name.lower() in n.lower():
                        self.combo_devices.current(idx)
                        matched = True
                        break
                if not matched and names:
                    self.combo_devices.current(0)
        except Exception as dev_err:
            logger.error(f"Error enumerating audio devices for combobox: {dev_err}")

        # Update Voice backend pill
        try:
            if hasattr(self, "pill_voice_backend"):
                backend = self.engine.voice_engine.get_backend_type()
                state = "FALLBACK" if "sounddevice" in backend.lower() else "ACTIVE"
                self.pill_voice_backend.set_state(state)
        except Exception as pill_err:
            logger.error(f"Error updating voice backend status pill: {pill_err}")

    def _on_device_selected(self, event) -> None:
        """Handle user changing input microphone in combobox."""
        if not hasattr(self, "combo_devices"):
            return
        selected = self.combo_devices.get()
        if selected and selected.startswith("["):
            try:
                idx_str = selected.split("]")[0][1:]
                dev_idx = int(idx_str)
                self.engine.voice_engine.set_device(dev_idx)
                self.log_activity("SYSTEM", f"Audio input changed to {selected}")
                if hasattr(self, "pill_voice_backend"):
                    backend = self.engine.voice_engine.get_backend_type()
                    state = "FALLBACK" if "sounddevice" in backend.lower() else "ACTIVE"
                    self.pill_voice_backend.set_state(state)
            except Exception as exc:
                logger.error(f"Error parsing device index: {exc}")

    def _on_toggle_mic(self) -> None:
        """Toggle microphone on/off."""
        if self.engine.voice_engine.is_mic_enabled():
            self.engine.voice_engine.disable_mic()
            self.btn_mic_toggle.config(text="MIC OFF", fg=config.COLOR_RED_NEON)
            self.pill_voice_status.set_state("OFF")
            self.waveform.set_state("OFF")
        else:
            self.engine.voice_engine.enable_mic()
            self.btn_mic_toggle.config(text="MIC ON", fg=config.COLOR_GREEN_NEON)
            self.pill_voice_status.set_state("LISTENING")
            self.waveform.set_state("LISTENING")

    def _on_toggle_camera(self) -> None:
        """Toggle gesture camera on/off."""
        if self.engine.gesture_engine.is_camera_enabled():
            self.engine.gesture_engine.disable_camera()
            self.btn_cam_toggle.config(text="CAM OFF", fg=config.COLOR_RED_NEON)
            self.pill_cam_status.set_state("OFF")
            self.pill_hand.set_state("NO")
            self.pill_gesture_mode.set_state("IDLE")
        else:
            self.engine.gesture_engine.enable_camera()
            self.btn_cam_toggle.config(text="CAM ON", fg=config.COLOR_PURPLE_NEON)
            self.pill_cam_status.set_state("ACTIVE")

    def _on_toggle_gesture_voice(self) -> None:
        """Toggle spoken voice confirmations for gestures."""
        config.GESTURE_VOICE_FEEDBACK_ENABLED = not config.GESTURE_VOICE_FEEDBACK_ENABLED
        lbl = "VOICE: ON" if config.GESTURE_VOICE_FEEDBACK_ENABLED else "VOICE: OFF"
        color = config.COLOR_CYAN_NEON if config.GESTURE_VOICE_FEEDBACK_ENABLED else config.COLOR_TEXT_DIM
        self.btn_gesture_voice.config(text=lbl, fg=color)
        self.log_activity("SYSTEM", f"Gesture Voice Announcements: {lbl}")

    def _on_recalibrate_noise(self) -> None:
        """Trigger on-demand noise calibration."""
        self.log_activity("SYSTEM", "Calibrating ambient noise...")
        self.engine.voice_engine.recalibrate_ambient_noise()

    def _on_submit_text_cmd(self) -> None:
        """Process typed command from entry box."""
        cmd = self.cmd_entry.get().strip()
        if not cmd:
            return
        self.cmd_entry.delete(0, tk.END)
        # Execute asynchronously in thread so GUI never hangs
        threading.Thread(
            target=self.engine.process_text_command,
            args=(cmd,),
            name="SYRAX-TextCmd-Worker",
            daemon=True
        ).start()

    def _on_confirm_send(self) -> None:
        """User clicked GUI SEND button to approve pending WhatsApp message."""
        if hasattr(self, "confirmation_frame"):
            self.confirmation_frame.pack_forget()
        threading.Thread(
            target=self.engine.process_text_command,
            args=("yes",),
            name="SYRAX-ConfirmSend-Worker",
            daemon=True
        ).start()

    def _on_confirm_cancel(self) -> None:
        """User clicked GUI CANCEL button to reject pending WhatsApp message."""
        if hasattr(self, "confirmation_frame"):
            self.confirmation_frame.pack_forget()
        threading.Thread(
            target=self.engine.process_text_command,
            args=("cancel",),
            name="SYRAX-ConfirmCancel-Worker",
            daemon=True
        ).start()

    def _on_cancel_current_operation(self) -> None:
        """Universal Emergency Stop / Cancel button clicked."""
        if hasattr(self, "confirmation_frame"):
            self.confirmation_frame.pack_forget()
        # Trigger global high-priority interrupt
        self.engine.interrupt_manager.trigger_interrupt(reason="Dashboard Emergency Stop Button")
        self.log_activity("SYSTEM", "Universal Cancel: Halting active operation, purging speech, stopping media.")
        threading.Thread(
            target=self.engine.process_text_command,
            args=("stop",),
            name="SYRAX-CancelOp-Worker",
            daemon=True
        ).start()

    def _on_run_diagnostics(self) -> None:
        """Run system diagnostics suite and log results."""
        self.log_activity("SYSTEM", "=== RUNNING SYSTEM DIAGNOSTICS ===")
        threading.Thread(
            target=self.engine.run_diagnostics,
            name="SYRAX-Diag-Worker",
            daemon=True
        ).start()

    def _on_clear_history(self) -> None:
        """Clear activity history log."""
        self.history_text.delete("1.0", tk.END)

    def on_close(self) -> None:
        """Gracefully shut down all engines and close the GUI."""
        logger.info("Dashboard close requested. Terminating assistant engine...")
        try:
            self.engine.stop()
        except Exception as exc:
            logger.error(f"Error during assistant shutdown: {exc}")
        finally:
            self.root.destroy()
