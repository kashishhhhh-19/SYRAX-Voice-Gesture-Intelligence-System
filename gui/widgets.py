"""
gui/widgets.py - Futuristic Cyberpunk Custom UI Widgets for SYRAX
Includes animated canvas waveform visualizer, camera preview widget with HUD,
neon status badges, framed sci-fi cards, and glowing interactive buttons.
"""

import math
import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional

import numpy as np
from PIL import Image, ImageTk

import config


class WaveformVisualizer(tk.Canvas):
    """
    Canvas-based multi-harmonic sinusoidal waveform visualizer.
    Smoothly animates in real-time, responding dynamically to state:
    - OFF: Flat dim horizontal line
    - IDLE: Gentle slow ambient blue wave
    - LISTENING: Energetic high-amplitude cyan wave reacting to speech
    - PROCESSING: Concentric rippling interference wave
    - SPEAKING: Multi-colored vibrant harmonics (cyan, green, blue)
    """

    def __init__(self, parent: tk.Widget, width: int = 400, height: int = 80, **kwargs) -> None:
        super().__init__(
            parent,
            width=width,
            height=height,
            bg=config.COLOR_BG_DARK,
            highlightthickness=1,
            highlightbackground=config.COLOR_BORDER,
            **kwargs
        )
        self._width = width
        self._height = height
        self._phase = 0.0
        self._state = "IDLE"  # OFF, IDLE, LISTENING, PROCESSING, SPEAKING
        self._animating = False

        self.bind("<Configure>", self._on_resize)
        self.start_animation()

    def _on_resize(self, event) -> None:
        self._width = max(10, event.width)
        self._height = max(10, event.height)

    def set_state(self, state: str) -> None:
        """Set visualization state."""
        self._state = state.upper()

    def start_animation(self) -> None:
        if not self._animating:
            self._animating = True
            self._render_frame()

    def stop_animation(self) -> None:
        self._animating = False

    def _render_frame(self) -> None:
        if not self._animating:
            return

        self.delete("all")
        mid_y = self._height / 2
        w = self._width

        # Background grid scan lines
        self.create_line(0, mid_y, w, mid_y, fill="#111c30", width=1)

        if self._state == "OFF":
            # Flat inactive line with subtle dot
            self.create_line(0, mid_y, w, mid_y, fill=config.COLOR_TEXT_DIM, width=1, dash=(4, 4))
            self.create_text(
                w / 2, mid_y - 12,
                text="VOICE CAPTURE DISABLED",
                fill=config.COLOR_TEXT_DIM,
                font=(config.FONT_MONO, 8)
            )

        elif self._state == "IDLE":
            # Ambient gentle undulating wave
            self._phase += 0.04
            points = []
            for x in range(0, w, 4):
                envelope = math.sin(x / w * math.pi)
                y = mid_y + math.sin(x * 0.03 + self._phase) * 8 * envelope
                points.extend([x, y])
            if len(points) >= 4:
                self.create_line(points, fill=config.COLOR_BLUE_NEON, width=2, smooth=True)

        elif self._state == "LISTENING":
            # Energetic high-amplitude cyan waves
            self._phase += 0.12
            # Primary wave
            points1 = []
            for x in range(0, w, 3):
                envelope = math.sin(x / w * math.pi)
                y = mid_y + (
                    math.sin(x * 0.05 + self._phase) * 22 +
                    math.sin(x * 0.12 - self._phase * 1.5) * 10
                ) * envelope
                points1.extend([x, y])
            # Harmonic wave
            points2 = []
            for x in range(0, w, 3):
                envelope = math.sin(x / w * math.pi)
                y = mid_y + (
                    math.cos(x * 0.04 - self._phase) * 16 +
                    math.sin(x * 0.08 + self._phase * 2) * 8
                ) * envelope
                points2.extend([x, y])

            if len(points2) >= 4:
                self.create_line(points2, fill=config.COLOR_BLUE_NEON, width=1, smooth=True)
            if len(points1) >= 4:
                self.create_line(points1, fill=config.COLOR_CYAN_NEON, width=2, smooth=True)

        elif self._state == "PROCESSING":
            # Rapid pulsating shimmer
            self._phase += 0.20
            points = []
            for x in range(0, w, 4):
                envelope = math.sin(x / w * math.pi)
                y = mid_y + math.sin(x * 0.1 + self._phase * 3) * 14 * envelope
                points.extend([x, y])
            if len(points) >= 4:
                self.create_line(points, fill=config.COLOR_YELLOW_NEON, width=2, smooth=True)

        elif self._state == "SPEAKING":
            # Vibrant multi-harmonic speech output wave
            self._phase += 0.14
            for offset, color, width in [
                (0.0, config.COLOR_GREEN_NEON, 2),
                (0.5, config.COLOR_CYAN_NEON, 1),
                (-0.5, config.COLOR_PURPLE_NEON, 1)
            ]:
                points = []
                for x in range(0, w, 3):
                    envelope = math.sin(x / w * math.pi)
                    y = mid_y + (
                        math.sin(x * 0.06 + self._phase + offset) * 20 +
                        math.cos(x * 0.14 + self._phase * 2) * 12
                    ) * envelope
                    points.extend([x, y])
                if len(points) >= 4:
                    self.create_line(points, fill=color, width=width, smooth=True)

        # Pulse loop ~30 FPS
        self.after(35, self._render_frame)


class CameraPreviewWidget(tk.Canvas):
    """
    Direct canvas renderer for video preview frames with HUD reticles.
    Automatically handles aspect-ratio scaling and standby graphics.
    """

    def __init__(self, parent: tk.Widget, width: int = 240, height: int = 160, **kwargs) -> None:
        super().__init__(
            parent,
            width=width,
            height=height,
            bg=config.COLOR_BG_DARK,
            highlightthickness=1,
            highlightbackground=config.COLOR_BORDER,
            **kwargs
        )
        self._target_w = width
        self._target_h = height
        self._photo_image: Optional[ImageTk.PhotoImage] = None
        self._show_standby()

    def update_frame(self, rgb_array: np.ndarray) -> None:
        """Update canvas with newly arrived RGB numpy frame."""
        try:
            img = Image.fromarray(rgb_array)
            img = img.resize((self._target_w, self._target_h), Image.Resampling.BILINEAR)
            self._photo_image = ImageTk.PhotoImage(image=img)
            self.delete("all")
            self.create_image(0, 0, anchor=tk.NW, image=self._photo_image)
        except Exception:
            self._show_standby()

    def _show_standby(self) -> None:
        """Render standby futuristic HUD visual."""
        self.delete("all")
        mid_x = self._target_w / 2
        mid_y = self._target_h / 2

        # Standby crosshairs
        self.create_line(mid_x - 30, mid_y, mid_x + 30, mid_y, fill=config.COLOR_BORDER, width=1)
        self.create_line(mid_x, mid_y - 20, mid_x, mid_y + 20, fill=config.COLOR_BORDER, width=1)
        self.create_rectangle(
            mid_x - 40, mid_y - 30, mid_x + 40, mid_y + 30,
            outline="#1e293b", width=1, dash=(3, 3)
        )
        self.create_text(
            mid_x, mid_y + 40,
            text="CAM STANDBY / OFF",
            fill=config.COLOR_TEXT_DIM,
            font=(config.FONT_MONO, 8)
        )


class NeonCard(tk.Frame):
    """
    Styled elevated card panel with neon title bar and dark background.
    """

    def __init__(
        self,
        parent: tk.Widget,
        title: str = "",
        accent_color: str = config.COLOR_CYAN_NEON,
        **kwargs
    ) -> None:
        super().__init__(
            parent,
            bg=config.COLOR_BG_CARD,
            highlightthickness=1,
            highlightbackground=config.COLOR_BORDER,
            padx=10,
            pady=10,
            **kwargs
        )
        self.accent_color = accent_color

        if title:
            # Header container
            header = tk.Frame(self, bg=config.COLOR_BG_CARD)
            header.pack(fill=tk.X, pady=(0, 8))

            # Indicator dot
            dot = tk.Canvas(header, width=8, height=8, bg=config.COLOR_BG_CARD, highlightthickness=0)
            dot.create_oval(1, 1, 7, 7, fill=accent_color, outline=accent_color)
            dot.pack(side=tk.LEFT, padx=(0, 6))

            # Title label
            lbl = tk.Label(
                header,
                text=title.upper(),
                bg=config.COLOR_BG_CARD,
                fg=config.COLOR_TEXT_PRIMARY,
                font=(config.FONT_FAMILY, 9, "bold")
            )
            lbl.pack(side=tk.LEFT)


class StatusPill(tk.Label):
    """
    Compact glowing status pill badge.
    """

    def __init__(self, parent: tk.Widget, text: str = "OFF", **kwargs) -> None:
        super().__init__(
            parent,
            text=text.upper(),
            bg="#111c30",
            fg=config.COLOR_TEXT_DIM,
            font=(config.FONT_MONO, 8, "bold"),
            padx=8,
            pady=2,
            relief=tk.FLAT,
            **kwargs
        )
        self.set_state(text)

    def set_state(self, state: str) -> None:
        """Update badge text and colors based on status."""
        st = state.upper()
        self.config(text=st)

        if st in ("ACTIVE", "ON", "LISTENING", "PASS", "CONNECTED", "YOUTUBE FOCUSED", "PYAUDIO"):
            self.config(bg="#052e16", fg=config.COLOR_GREEN_NEON)
        elif st in ("PROCESSING", "SPEAKING", "CALIBRATING", "SWITCHING FOCUS", "FALLBACK", "SOUNDDEVICE"):
            self.config(bg="#2d2005", fg=config.COLOR_YELLOW_NEON)
        elif st in ("STANDBY", "IDLE", "YOUTUBE DETECTED"):
            self.config(bg="#082f49", fg=config.COLOR_CYAN_NEON)
        elif st in ("OFF", "MUTED", "FAIL", "DISCONNECTED", "ERROR", "YOUTUBE NOT FOUND"):
            self.config(bg="#3b0714", fg=config.COLOR_RED_NEON)
        else:
            self.config(bg="#111c30", fg=config.COLOR_TEXT_MUTED)


class NeonButton(tk.Button):
    """
    Futuristic sci-fi styled button with hover glow transitions.
    """

    def __init__(
        self,
        parent: tk.Widget,
        text: str,
        command: Optional[Callable[[], None]] = None,
        accent_color: str = config.COLOR_CYAN_NEON,
        width: int = 14,
        **kwargs
    ) -> None:
        self.accent_color = accent_color
        self._default_bg = config.COLOR_BG_PANEL
        self._hover_bg = "#1b2a4a"

        super().__init__(
            parent,
            text=text.upper(),
            command=command,
            bg=self._default_bg,
            fg=config.COLOR_TEXT_PRIMARY,
            activebackground=accent_color,
            activeforeground="#000000",
            font=(config.FONT_FAMILY, 9, "bold"),
            relief=tk.FLAT,
            highlightthickness=1,
            highlightbackground=config.COLOR_BORDER,
            padx=10,
            pady=4,
            cursor="hand2",
            width=width,
            **kwargs
        )

        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)

    def _on_enter(self, event) -> None:
        self.config(bg=self._hover_bg, fg=self.accent_color, highlightbackground=self.accent_color)

    def _on_leave(self, event) -> None:
        self.config(bg=self._default_bg, fg=config.COLOR_TEXT_PRIMARY, highlightbackground=config.COLOR_BORDER)
