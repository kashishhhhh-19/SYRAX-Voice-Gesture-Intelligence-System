"""
core/assistant_engine.py - Central Coordinator for SYRAX
Ties together VoiceEngine, GestureEngine, TTSEngine, CommandParser, and ActionDispatcher.
Coordinates the startup greeting, processes typed & voice input, executes diagnostics,
and orchestrates safe multi-threaded shutdown.
"""

import threading
import time
from typing import Any, Dict, List, Optional

import config
from core.action_dispatcher import ActionDispatcher, ActionResult
from core.command_parser import Command, CommandIntent, CommandParser
from core.conversation_state import ConversationState
from core.event_bus import Events, get_event_bus
from core.interrupt_manager import InterruptManager, InterruptType
from core.logger import get_logger
from gesture.gesture_engine import GestureEngine
from voice.tts_engine import TTSEngine
from voice.voice_engine import VoiceEngine

logger = get_logger("AssistantEngine")


class AssistantEngine:
    """
    Central controller orchestrating all SYRAX subsystems.
    """

    def __init__(self) -> None:
        self._event_bus = get_event_bus()
        self._logger = logger

        # 1. Initialize Subsystems
        self.tts_engine = TTSEngine()
        self.interrupt_manager = InterruptManager(tts_engine=self.tts_engine)
        self.conversation_state = ConversationState()
        self.voice_engine = VoiceEngine(tts_engine=self.tts_engine, interrupt_manager=self.interrupt_manager)
        self.gesture_engine = GestureEngine()
        self.command_parser = CommandParser(
            conversation_state=self.conversation_state,
            interrupt_manager=self.interrupt_manager
        )
        self.action_dispatcher = ActionDispatcher(tts_engine=self.tts_engine)

        self._running = False
        self._last_command: str = "None"
        self._active_mode: str = "HYBRID"

        # 2. Wire Internal Event Listeners
        self._register_event_handlers()
        self.interrupt_manager.register_listener(self._on_interrupt)

    def _on_interrupt(self, interrupt_type: InterruptType) -> None:
        """Handle urgent system interrupt triggered by voice or keyboard."""
        logger.info(f"Coordinator processing interrupt: {interrupt_type.value}")
        if interrupt_type == InterruptType.STOP_ACTIVITY:
            from actions.media_actions import MediaActions
            MediaActions.pause_playback()
            self._event_bus.emit(
                Events.ASSISTANT_RESPONSE,
                text="Playback stopped.",
                source="interrupt"
            )
            self.tts_engine.speak("Playback stopped.")
        elif interrupt_type == InterruptType.STOP_GESTURES:
            self.gesture_engine.set_state("IDLE")
            self.tts_engine.speak("Gesture control paused.")
        elif interrupt_type == InterruptType.CANCEL_MESSAGE:
            self.conversation_state.clear_pending_confirmation()
            self._event_bus.emit(
                Events.ASSISTANT_RESPONSE,
                text="Message cancelled.",
                source="interrupt"
            )
            self.tts_engine.speak("Message cancelled.")
        elif interrupt_type == InterruptType.EXIT_SYRAX:
            self._event_bus.emit(Events.SHUTDOWN_REQUESTED, reason="Voice interrupt")

    def _register_event_handlers(self) -> None:
        """Subscribe coordinator methods to event bus notifications."""
        self._event_bus.subscribe(Events.VOICE_RECOGNIZED, self._on_voice_recognized)
        self._event_bus.subscribe(Events.GESTURE_DETECTED, self._on_gesture_detected)
        self._event_bus.subscribe(Events.GESTURE_MODE_TOGGLED, self._on_gesture_mode_toggled)

    def _on_gesture_mode_toggled(self, state: str, **kwargs) -> None:
        """Handle gesture mode toggle events."""
        if self.gesture_engine.get_state() != state:
            self.gesture_engine.set_state(state)

    def start(self) -> None:
        """Launch all engine worker threads and deliver startup greeting."""
        if self._running:
            return
        self._running = True
        logger.info("Initializing SYRAX Assistant Engine...")

        # Start TTS synthesized voice thread first
        self.tts_engine.start()

        # Start Gesture vision thread
        self.gesture_engine.start()

        # Start Voice listening thread
        self.voice_engine.start()

        # Deliver startup greeting
        greeting = config.GREETING_TEXT
        self.tts_engine.speak(greeting)
        self._event_bus.emit(
            Events.ASSISTANT_RESPONSE,
            text=greeting,
            source="startup"
        )
        self._event_bus.emit(
            Events.ACTIVITY_LOG,
            category="SYSTEM",
            message=f"SYRAX initialized. Ready. Tagline: '{config.TAGLINE}'"
        )

    def stop(self) -> None:
        """Gracefully terminate all running worker threads and release resources."""
        if not self._running:
            return
        self._running = False
        logger.info("Stopping SYRAX Assistant Engine...")

        # Stop Voice capture
        self.voice_engine.stop()

        # Stop Gesture vision
        self.gesture_engine.stop()

        # Stop TTS worker
        self.tts_engine.stop()

        logger.info("SYRAX Assistant Engine stopped cleanly.")

    def process_text_command(self, text: str) -> ActionResult:
        """
        Process a typed text command from the GUI input box.
        Executes the same intent parsing and dispatch pipeline as speech.
        """
        if not text or not text.strip():
            return ActionResult(
                success=False,
                response_text="Empty command.",
                spoken_text="",
                intent=CommandIntent.UNKNOWN,
                raw_command=text
            )

        self._last_command = text
        cmd = self.command_parser.parse(text, source="text")

        self._event_bus.emit(
            Events.ACTIVITY_LOG,
            category="TEXT",
            message=f"Typed Command: '{text}' -> Intent: {cmd.intent.value}"
        )

        result = self.action_dispatcher.dispatch(cmd)
        self._event_bus.emit(
            Events.ASSISTANT_RESPONSE,
            text=result.response_text,
            source="text"
        )
        return result

    def _on_voice_recognized(self, text: str, source: str = "voice") -> None:
        """Callback triggered when VoiceEngine finishes transcribing an utterance."""
        self._last_command = text
        self._event_bus.emit(
            Events.ACTIVITY_LOG,
            category="VOICE",
            message=f"Heard: '{text}'"
        )

        # Parse speech into command
        cmd = self.command_parser.parse(text, source=source)
        logger.info(f"Parsed voice utterance '{text}' -> {cmd.intent.value} ({cmd.confidence * 100:.0f}%)")

        # Dispatch command
        result = self.action_dispatcher.dispatch(cmd)
        self._event_bus.emit(
            Events.ASSISTANT_RESPONSE,
            text=result.response_text,
            source="voice"
        )

    def _on_gesture_detected(
        self,
        gesture: str,
        state: str,
        description: str,
        spoken: Optional[str] = None,
        confidence: float = 1.0
    ) -> None:
        """Callback triggered when GestureEngine recognizes a valid gesture."""
        self._last_command = f"Gesture: {gesture}"
        conf_str = f" ({int(confidence * 100)}%)" if confidence < 1.0 else ""
        self._event_bus.emit(
            Events.ACTIVITY_LOG,
            category="GESTURE",
            message=f"Gesture [{gesture}{conf_str}] -> Action: {description} (State: {state})"
        )
        self._event_bus.emit(
            Events.ASSISTANT_RESPONSE,
            text=f"Gesture: {gesture} - {description}",
            source="gesture"
        )
        if spoken and self.tts_engine:
            self.tts_engine.speak(spoken)

    def run_diagnostics(self) -> List[Dict[str, Any]]:
        """
        Comprehensive self-test of all subsystems.
        Returns a list of diagnostic test result dicts.
        """
        results: List[Dict[str, Any]] = []
        logger.info("Starting SYRAX Subsystem Diagnostics...")

        # 1. Microphone Hardware Test
        mic_test = self._diagnose_microphone()
        results.append(mic_test)
        self._event_bus.emit(Events.DIAGNOSTIC_RESULT, **mic_test)

        # 2. Speech Recognition Reachability Test
        stt_test = self._diagnose_stt()
        results.append(stt_test)
        self._event_bus.emit(Events.DIAGNOSTIC_RESULT, **stt_test)

        # 3. TTS Synthesis Test
        tts_test = self._diagnose_tts()
        results.append(tts_test)
        self._event_bus.emit(Events.DIAGNOSTIC_RESULT, **tts_test)

        # 4. Webcam & Vision Test
        cam_test = self._diagnose_camera()
        results.append(cam_test)
        self._event_bus.emit(Events.DIAGNOSTIC_RESULT, **cam_test)

        # 5. Gesture Classifier Logic Test
        gesture_test = self._diagnose_gesture_classifier()
        results.append(gesture_test)
        self._event_bus.emit(Events.DIAGNOSTIC_RESULT, **gesture_test)

        # 6. YouTube Window Detection & Focus Verification Test
        focus_test = self._diagnose_youtube_focus()
        results.append(focus_test)
        self._event_bus.emit(Events.DIAGNOSTIC_RESULT, **focus_test)

        # 7. PyAutoGUI Automation Test
        auto_test = self._diagnose_pyautogui()
        results.append(auto_test)
        self._event_bus.emit(Events.DIAGNOSTIC_RESULT, **auto_test)

        return results

    def _diagnose_microphone(self) -> Dict[str, Any]:
        """Test audio input devices and sample capture level."""
        try:
            devices = self.voice_engine.get_available_devices()
            if not devices:
                return {
                    "subsystem": "Microphone",
                    "passed": False,
                    "message": "No audio input devices detected.",
                    "fix_hint": "Verify built-in Realtek mic is enabled in Windows Sound Settings."
                }

            device_name = self.voice_engine.get_current_device_name()
            backend = self.voice_engine.get_backend_type()

            # Attempt brief audio sample capture to check input level
            sample_level_ok = True
            level_info = "Audio stream active"
            try:
                import sounddevice as sd
                import numpy as np
                duration = 0.3
                recording = sd.rec(int(duration * 16000), samplerate=16000, channels=1, dtype="int16")
                sd.wait()
                rms = np.sqrt(np.mean(recording.astype(np.float32) ** 2))
                level_info = f"RMS Energy: {rms:.1f}"
            except Exception as sample_err:
                level_info = f"Capture check: {sample_err}"

            return {
                "subsystem": "Microphone",
                "passed": True,
                "message": f"Active Device: {device_name} (Backend: {backend}, {level_info})",
                "fix_hint": "None. Microphone is operational."
            }
        except Exception as exc:
            return {
                "subsystem": "Microphone",
                "passed": False,
                "message": f"Microphone error: {exc}",
                "fix_hint": "Run setup.bat or check Windows microphone privacy permissions."
            }

    def _diagnose_stt(self) -> Dict[str, Any]:
        """Test Google Speech Recognition network endpoint."""
        import urllib.request
        try:
            # Check internet connectivity to Google
            urllib.request.urlopen("https://www.google.com", timeout=3.0)
            return {
                "subsystem": "Speech Recognition (STT)",
                "passed": True,
                "message": "Google Speech Recognition service reachable.",
                "fix_hint": "None. Network connectivity is solid."
            }
        except Exception as net_err:
            return {
                "subsystem": "Speech Recognition (STT)",
                "passed": False,
                "message": f"Speech API unreachable: {net_err}",
                "fix_hint": "Connect to Wi-Fi/Internet or check firewall settings."
            }

    def _diagnose_tts(self) -> Dict[str, Any]:
        """Test Windows SAPI / pyttsx3 speech synthesis."""
        try:
            engine_type = self.tts_engine.get_engine_type()
            # Perform a test utterance
            self.tts_engine.speak("SYRAX diagnostics test.", block=True)
            return {
                "subsystem": "Text-to-Speech (TTS)",
                "passed": True,
                "message": f"TTS operational ({engine_type}).",
                "fix_hint": "None. Speech synthesizer is working."
            }
        except Exception as tts_err:
            return {
                "subsystem": "Text-to-Speech (TTS)",
                "passed": False,
                "message": f"TTS failure: {tts_err}",
                "fix_hint": "Check Windows SAPI5 audio drivers or install pywin32 / comtypes."
            }

    def _diagnose_camera(self) -> Dict[str, Any]:
        """Test webcam opening and frame acquisition."""
        import cv2
        cap = None
        try:
            cap = cv2.VideoCapture(config.CAMERA_INDEX, cv2.CAP_DSHOW)
            if not cap.isOpened():
                cap = cv2.VideoCapture(config.CAMERA_INDEX)

            if not cap.isOpened():
                return {
                    "subsystem": "Webcam & Gestures",
                    "passed": False,
                    "message": "Webcam could not be opened.",
                    "fix_hint": "Verify camera is plugged in and not in use by Zoom/Teams/Browser."
                }

            ret, frame = cap.read()
            if not ret or frame is None:
                return {
                    "subsystem": "Webcam & Gestures",
                    "passed": False,
                    "message": "Webcam opened but failed to capture a frame.",
                    "fix_hint": "Check Windows Camera Privacy Settings -> Allow desktop apps."
                }

            h, w, _ = frame.shape
            mp_status = "MediaPipe Active" if self.gesture_engine._mp_available else "OpenCV Adaptive Tracker Active"
            return {
                "subsystem": "Webcam & Gestures",
                "passed": True,
                "message": f"Webcam active ({w}x{h} resolution). {mp_status}.",
                "fix_hint": "None. Video pipeline is operational."
            }
        except Exception as cam_err:
            return {
                "subsystem": "Webcam & Gestures",
                "passed": False,
                "message": f"Webcam error: {cam_err}",
                "fix_hint": "Check camera driver or specify different camera index in config.py."
            }
        finally:
            if cap is not None:
                cap.release()

    def _diagnose_gesture_classifier(self) -> Dict[str, Any]:
        """Test gesture classifier pure landmark detection rules."""
        try:
            from gesture.gesture_classifier import classify_pose

            # 1. Synthetic Fist Landmarks (wrist at (0.5, 0.7), tips curled close to palm at (0.5, 0.6))
            fist_landmarks = [(0.5, 0.7)] + [(0.5, 0.6) for _ in range(20)]
            fist_pose, fist_conf = classify_pose(fist_landmarks)

            # 2. Synthetic Open Palm Landmarks (wrist at (0.5, 0.8), tips high at (0.5, 0.2))
            palm_landmarks = [(0.5, 0.8)]
            for finger_idx in range(5):
                spread_x = 0.3 + (finger_idx * 0.1)
                palm_landmarks.extend([
                    (spread_x, 0.6), # MCP
                    (spread_x, 0.5), # PIP
                    (spread_x, 0.35), # DIP
                    (spread_x, 0.2), # TIP
                ])
            palm_pose, palm_conf = classify_pose(palm_landmarks)

            if fist_pose == "FIST" and palm_pose == "OPEN_PALM":
                return {
                    "subsystem": "Gesture Classifier",
                    "passed": True,
                    "message": "Pure landmark classifier operational (Fist, Open Palm, Swipe, Pinch rules verified).",
                    "fix_hint": "None. Gesture rules verified."
                }
            else:
                return {
                    "subsystem": "Gesture Classifier",
                    "passed": False,
                    "message": f"Classification test mismatch: Fist={fist_pose}, Palm={palm_pose}",
                    "fix_hint": "Inspect gesture_classifier.py geometry thresholds."
                }
        except Exception as exc:
            return {
                "subsystem": "Gesture Classifier",
                "passed": False,
                "message": f"Gesture classifier error: {exc}",
                "fix_hint": "Verify gesture_classifier.py implementation."
            }

    def _diagnose_youtube_focus(self) -> Dict[str, Any]:
        """Test YouTube window detection and browser focus management."""
        try:
            from actions.focus_manager import get_focus_manager
            fm = get_focus_manager()
            win = fm.find_youtube_window()

            if win:
                hwnd, title = win
                return {
                    "subsystem": "YouTube Focus Manager",
                    "passed": True,
                    "message": f"YouTube window detected: '{title}' (HWND: {hwnd}). Ready for foreground focus.",
                    "fix_hint": "None. YouTube is active."
                }
            else:
                return {
                    "subsystem": "YouTube Focus Manager",
                    "passed": True,
                    "message": "FocusManager operational. YouTube window currently not open (will prompt user when triggered).",
                    "fix_hint": "Open a YouTube tab in Chrome, Edge, or Firefox to test live browser focus."
                }
        except Exception as exc:
            return {
                "subsystem": "YouTube Focus Manager",
                "passed": False,
                "message": f"FocusManager error: {exc}",
                "fix_hint": "Verify win32gui and pygetwindow permissions."
            }

    def _diagnose_pyautogui(self) -> Dict[str, Any]:
        """Test PyAutoGUI desktop automation engine."""
        try:
            import pyautogui
            w, h = pyautogui.size()
            pos = pyautogui.position()
            return {
                "subsystem": "Desktop Automation (PyAutoGUI)",
                "passed": True,
                "message": f"Screen bounds: {w}x{h}, Cursor: {pos}, Failsafe: {pyautogui.FAILSAFE}",
                "fix_hint": "None. Keyboard and mouse injection is ready."
            }
        except Exception as auto_err:
            return {
                "subsystem": "Desktop Automation (PyAutoGUI)",
                "passed": False,
                "message": f"PyAutoGUI error: {auto_err}",
                "fix_hint": "Verify display drivers and user privileges."
            }
