"""
voice/voice_engine.py - Speech Recognition & Microphone Capture for SYRAX
Prioritizes PyAudio with automatic drop-in fallback to sounddevice.
Optimized for built-in Realtek laptop microphones at normal speaking distance.
Includes dynamic ambient noise calibration, non-blocking background listening,
instant mic toggle, and automatic echo suppression during TTS speech output.
"""

import queue
import sys
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

import speech_recognition as sr

import config
from core.event_bus import Events, get_event_bus
from core.interrupt_manager import InterruptManager, InterruptType
from core.logger import get_logger
from voice.tts_engine import TTSEngine

logger = get_logger("VoiceEngine")


class SoundDeviceMicrophone(sr.AudioSource):
    """
    Drop-in replacement for speech_recognition.Microphone using sounddevice.
    Activated when PyAudio is not installed or when Windows audio driver requires it.
    Complies fully with speech_recognition.AudioSource contract.
    """

    def __init__(
        self,
        device_index: Optional[int] = None,
        sample_rate: int = config.DEFAULT_SAMPLE_RATE,
        chunk_size: int = config.CHUNK_SIZE
    ) -> None:
        self.device_index = device_index
        self.SAMPLE_RATE = sample_rate
        self.CHUNK = chunk_size
        self.SAMPLE_WIDTH = 2  # 16-bit integer PCM
        self._sd_stream = None
        self._audio_queue: queue.Queue[bytes] = queue.Queue()
        self.stream = None

    def __enter__(self) -> "SoundDeviceMicrophone":
        import sounddevice as sd

        self._audio_queue = queue.Queue()

        def _audio_callback(indata, frames, time_info, status):
            if status:
                logger.debug(f"SoundDevice status: {status}")
            self._audio_queue.put(bytes(indata))

        self._sd_stream = sd.RawInputStream(
            samplerate=self.SAMPLE_RATE,
            channels=1,
            dtype="int16",
            blocksize=self.CHUNK,
            device=self.device_index,
            callback=_audio_callback
        )
        self._sd_stream.start()

        class _SDStreamWrapper:
            def __init__(self, q: queue.Queue[bytes]):
                self._q = q

            def read(self, size: int) -> bytes:
                try:
                    return self._q.get(timeout=1.0)
                except queue.Empty:
                    return b"\x00" * size

            def close(self) -> None:
                pass

        self.stream = _SDStreamWrapper(self._audio_queue)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._sd_stream is not None:
            try:
                self._sd_stream.stop()
                self._sd_stream.close()
            except Exception as exc:
                logger.debug(f"Error closing sounddevice stream: {exc}")
            finally:
                self._sd_stream = None
        self.stream = None


class VoiceEngine:
    """
    Central speech capture and recognition engine.
    Runs continuous background recognition in an isolated daemon thread.
    """

    def __init__(
        self,
        tts_engine: Optional[TTSEngine] = None,
        interrupt_manager: Optional[InterruptManager] = None
    ) -> None:
        self._event_bus = get_event_bus()
        self._tts_engine = tts_engine
        self._interrupt_manager = interrupt_manager
        self._recognizer = sr.Recognizer()

        # Configure recognizer thresholds from config
        self._recognizer.energy_threshold = config.ENERGY_THRESHOLD
        self._recognizer.dynamic_energy_threshold = config.DYNAMIC_ENERGY_THRESHOLD
        self._recognizer.dynamic_energy_adjustment_damping = config.DYNAMIC_ENERGY_ADJUSTMENT_DAMPING
        self._recognizer.dynamic_energy_ratio = config.DYNAMIC_ENERGY_RATIO
        self._recognizer.pause_threshold = config.PAUSE_THRESHOLD

        self._running = False
        self._mic_enabled = True
        self._selected_device_index: Optional[int] = None
        self._selected_device_name: str = "Default System Microphone"
        self._backend_type: str = "unknown"

        self._consecutive_failures = 0
        self._worker_thread: Optional[threading.Thread] = None
        self._state_lock = threading.RLock()

        # Discover and select initial microphone
        self._init_microphone_source()

    def _init_microphone_source(self) -> None:
        """Probe available audio backends and select preferred input device."""
        devices = self.get_available_devices()

        # Find preferred microphone (e.g., built-in Realtek mic)
        preferred_idx = None
        for dev in devices:
            if config.PREFERRED_MIC_KEYWORD.lower() in dev["name"].lower():
                preferred_idx = dev["index"]
                self._selected_device_name = dev["name"]
                logger.info(f"Auto-selected Realtek microphone: {dev['name']} [Index {preferred_idx}]")
                break

        if preferred_idx is None and devices:
            preferred_idx = devices[0]["index"]
            self._selected_device_name = devices[0]["name"]
            logger.info(f"Using default input device: {devices[0]['name']} [Index {preferred_idx}]")

        self._selected_device_index = preferred_idx

    def get_available_devices(self) -> List[Dict[str, Any]]:
        """Enumerate all available physical audio input devices."""
        device_list: List[Dict[str, Any]] = []

        # 1. Try sounddevice
        try:
            import sounddevice as sd
            raw_devices = sd.query_devices()
            for idx, dev in enumerate(raw_devices):
                if dev.get("max_input_channels", 0) > 0:
                    device_list.append({
                        "index": idx,
                        "name": dev.get("name", f"Microphone {idx}"),
                        "channels": dev.get("max_input_channels"),
                        "sample_rate": int(dev.get("default_samplerate", config.DEFAULT_SAMPLE_RATE)),
                        "backend": "sounddevice"
                    })
            if device_list:
                return device_list
        except Exception as sd_err:
            logger.debug(f"sounddevice device enumeration failed: {sd_err}")

        # 2. Try PyAudio via speech_recognition
        try:
            names = sr.Microphone.list_microphone_names()
            for idx, name in enumerate(names):
                if name:
                    device_list.append({
                        "index": idx,
                        "name": name,
                        "channels": 1,
                        "sample_rate": config.DEFAULT_SAMPLE_RATE,
                        "backend": "pyaudio"
                    })
        except Exception as pa_err:
            logger.debug(f"PyAudio device enumeration failed: {pa_err}")

        return device_list

    def set_device(self, device_index: int) -> bool:
        """Switch the active input microphone to the specified index."""
        with self._state_lock:
            devices = self.get_available_devices()
            matched = next((d for d in devices if d["index"] == device_index), None)
            if not matched:
                logger.warning(f"Device index {device_index} not found.")
                return False

            self._selected_device_index = device_index
            self._selected_device_name = matched["name"]
            logger.info(f"Switched active microphone to: {matched['name']} [Index {device_index}]")
            self._event_bus.emit(
                Events.VOICE_DEVICE_CHANGED,
                device_index=device_index,
                device_name=matched["name"]
            )
            # Re-calibrate on device change
            self.recalibrate_ambient_noise()
            return True

    def get_current_device_name(self) -> str:
        """Return the label of the currently bound microphone."""
        return self._selected_device_name

    def get_backend_type(self) -> str:
        """Return the active capture backend (PyAudio or SoundDevice)."""
        return self._backend_type

    def _create_source(self) -> sr.AudioSource:
        """Create the appropriate AudioSource instance with fallback."""
        # Check PyAudio first
        try:
            import pyaudio
            source = sr.Microphone(
                device_index=self._selected_device_index,
                sample_rate=config.DEFAULT_SAMPLE_RATE,
                chunk_size=config.CHUNK_SIZE
            )
            self._backend_type = "PyAudio"
            return source
        except Exception as exc:
            logger.info(f"PyAudio unavailable ({exc}). Using sounddevice fallback.")
            self._backend_type = "sounddevice (Fallback)"
            return SoundDeviceMicrophone(
                device_index=self._selected_device_index,
                sample_rate=config.DEFAULT_SAMPLE_RATE,
                chunk_size=config.CHUNK_SIZE
            )

    def start(self) -> None:
        """Start the background speech recognition listening loop."""
        if self._running:
            return
        self._running = True
        self._worker_thread = threading.Thread(
            target=self._listen_loop,
            name="SYRAX-Voice-Worker",
            daemon=True
        )
        self._worker_thread.start()
        logger.info("VoiceEngine background listener started.")

    def stop(self) -> None:
        """Stop background listening cleanly."""
        self._running = False
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=1.5)
        logger.info("VoiceEngine stopped.")

    def enable_mic(self) -> None:
        """Unmute / resume voice capture."""
        with self._state_lock:
            self._mic_enabled = True
            logger.info("Microphone unmuted (ON).")
            self._event_bus.emit(
                Events.VOICE_STATUS_CHANGED,
                status="LISTENING",
                message="Listening for voice commands..."
            )

    def disable_mic(self) -> None:
        """Mute / pause voice capture instantly."""
        with self._state_lock:
            self._mic_enabled = False
            logger.info("Microphone muted (OFF).")
            self._event_bus.emit(
                Events.VOICE_STATUS_CHANGED,
                status="OFF",
                message="Microphone is disabled."
            )

    def is_mic_enabled(self) -> bool:
        """Return True if the microphone is currently active."""
        return self._mic_enabled

    def recalibrate_ambient_noise(self, duration: float = config.AMBIENT_CALIBRATION_DURATION) -> None:
        """Perform on-demand ambient noise adjustment in background thread."""
        threading.Thread(
            target=self._run_calibration,
            args=(duration,),
            name="SYRAX-Noise-Calibration",
            daemon=True
        ).start()

    def _run_calibration(self, duration: float) -> None:
        """Execute ambient noise sampling to adapt energy threshold."""
        try:
            self._event_bus.emit(
                Events.VOICE_STATUS_CHANGED,
                status="CALIBRATING",
                message="Calibrating for room noise... Please remain quiet."
            )
            source = self._create_source()
            with source as src:
                self._recognizer.adjust_for_ambient_noise(src, duration=duration)
            logger.info(f"Noise calibrated. Energy threshold set to: {self._recognizer.energy_threshold:.1f}")
            self._event_bus.emit(
                Events.VOICE_STATUS_CHANGED,
                status="LISTENING" if self._mic_enabled else "OFF",
                message="Listening for commands..." if self._mic_enabled else "Microphone is muted."
            )
        except Exception as exc:
            logger.error(f"Ambient noise calibration failed: {exc}")
            self._event_bus.emit(
                Events.VOICE_ERROR,
                error="CalibrationFailed",
                message=f"Could not calibrate mic: {exc}"
            )

    def set_interrupt_manager(self, interrupt_manager: InterruptManager) -> None:
        """Inject InterruptManager reference for high-priority cancel routing."""
        with self._state_lock:
            self._interrupt_manager = interrupt_manager

    def _listen_loop(self) -> None:
        """
        Continuous listening worker.
        Handles speech timeouts, ambient noise adjustment, and high-priority interrupt routing.
        Allows immediate interruption (e.g. 'Stop') even while TTS is speaking.
        """
        # Initial calibration
        self._run_calibration(duration=0.8)

        while self._running:
            # Check mic toggle
            if not self._mic_enabled:
                time.sleep(0.15)
                continue

            # Capture audio phrase
            try:
                source = self._create_source()
                with source as src:
                    # Update status to listening
                    self._event_bus.emit(
                        Events.VOICE_STATUS_CHANGED,
                        status="LISTENING",
                        message="Listening..."
                    )

                    audio_data = self._recognizer.listen(
                        src,
                        timeout=config.LISTEN_TIMEOUT,
                        phrase_time_limit=config.PHRASE_TIME_LIMIT
                    )

                # Recognize speech
                self._event_bus.emit(
                    Events.VOICE_STATUS_CHANGED,
                    status="PROCESSING",
                    message="Recognizing speech..."
                )

                transcript = self._recognizer.recognize_google(audio_data)
                logger.info(f"Speech Recognized: '{transcript}'")
                self._consecutive_failures = 0

                # 1. High-priority interrupt path (evaluated BEFORE normal processing)
                if self._interrupt_manager:
                    itype = self._interrupt_manager.check_for_interrupt_phrase(transcript)
                    if itype != InterruptType.NONE:
                        logger.info(f"Intercepted urgent voice interrupt: {itype.value}")
                        self._interrupt_manager.trigger_interrupt(itype, reason=f"Spoken: '{transcript}'")
                        self._event_bus.emit(
                            Events.VOICE_RECOGNIZED,
                            text=transcript,
                            source="voice"
                        )
                        continue

                # 2. Echo suppression: If TTS was speaking and utterance was NOT an interrupt, discard echo
                if self._tts_engine and self._tts_engine.is_speaking():
                    logger.debug(f"Discarding audio echo while speaking: '{transcript}'")
                    continue

                # 3. Publish recognized speech to system for normal action parsing
                self._event_bus.emit(
                    Events.VOICE_RECOGNIZED,
                    text=transcript,
                    source="voice"
                )

            except sr.WaitTimeoutError:
                # Normal silence timeout; loop cleanly
                continue

            except sr.UnknownValueError:
                # Audio captured but could not be parsed into words
                self._consecutive_failures += 1
                logger.debug(f"Unrecognized speech (Failure count: {self._consecutive_failures})")

                # Auto-recalibrate noise if repeated unrecognized audio
                if self._consecutive_failures >= config.MAX_CONSECUTIVE_VOICE_FAILURES:
                    logger.info("Repeated recognition misses. Auto-recalibrating ambient noise...")
                    self._run_calibration(duration=1.0)
                    self._consecutive_failures = 0

                self._event_bus.emit(
                    Events.VOICE_STATUS_CHANGED,
                    status="LISTENING",
                    message="Listening..."
                )

            except sr.RequestError as req_err:
                # Network or API service connectivity issue
                logger.error(f"Google Speech Recognition API unreachable: {req_err}")
                self._event_bus.emit(
                    Events.VOICE_ERROR,
                    error="RequestError",
                    message="Speech service unreachable. Please check internet connection."
                )
                time.sleep(2.0)

            except Exception as capture_err:
                # Physical microphone unplugged, permission denied, or audio device error
                logger.error(f"Microphone capture error: {capture_err}", exc_info=True)
                self._event_bus.emit(
                    Events.VOICE_ERROR,
                    error="MicrophoneUnavailable",
                    message=f"Microphone error: {capture_err}. Run 'python main.py --diagnose' to fix."
                )
                if self._tts_engine:
                    self._tts_engine.speak(config.RESPONSES["mic_unavailable"][0])
                time.sleep(3.0)
