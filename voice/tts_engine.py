"""
voice/tts_engine.py - High-Performance Text-to-Speech Engine for SYRAX
Prioritizes Windows SAPI (via comtypes/win32com) with non-blocking threaded queue,
and falls back gracefully to pyttsx3. Guarantees SYRAX never speaks over itself
and signals listening modules to prevent audio self-triggering loops.
"""

import queue
import threading
import time
from typing import Optional

import config
from core.event_bus import Events, get_event_bus
from core.logger import get_logger

logger = get_logger("TTSEngine")


class TTSEngine:
    """
    Non-blocking Text-To-Speech service with an asynchronous queue worker.
    """

    def __init__(self) -> None:
        self._event_bus = get_event_bus()
        self._speech_queue: queue.Queue[Optional[str]] = queue.Queue()
        self._is_speaking_flag = threading.Event()
        self._running = False
        self._worker_thread: Optional[threading.Thread] = None
        self._engine_type: str = "unknown"
        self._sapi_voice: Optional[Any] = None
        self._pyttsx_engine: Optional[Any] = None

    def start(self) -> None:
        """Start the background TTS synthesizer thread."""
        if self._running:
            return
        self._running = True
        self._worker_thread = threading.Thread(
            target=self._speech_worker,
            name="SYRAX-TTS-Worker",
            daemon=True
        )
        self._worker_thread.start()
        logger.info("TTS Engine background worker started.")

    def stop(self) -> None:
        """Stop TTS worker and release COM resources cleanly."""
        self._running = False
        self._speech_queue.put(None)  # Sentinel to unblock queue
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=1.5)
        self._is_speaking_flag.clear()
        logger.info("TTS Engine stopped.")

    def speak(self, text: str, block: bool = False) -> None:
        """
        Enqueue text for spoken synthesis.
        If block is True, wait until utterance completes.
        """
        if not text or not text.strip():
            return

        clean_text = text.strip()
        logger.debug(f"Queueing TTS utterance: '{clean_text}'")

        if block:
            self._speak_direct(clean_text)
        else:
            self._speech_queue.put(clean_text)

    def is_speaking(self) -> bool:
        """Return True if TTS is actively producing sound."""
        return self._is_speaking_flag.is_set()

    def stop_speaking(self) -> None:
        """Immediately halt active speech output and purge queued utterances."""
        logger.info("Interrupting TTS speech output (purge).")
        # 1. Drain pending queue
        while not self._speech_queue.empty():
            try:
                self._speech_queue.get_nowait()
                self._speech_queue.task_done()
            except Exception:
                break

        # 2. Purge active SAPI voice (Flag 2 = SVSFPurgeBeforeSpeak)
        if self._sapi_voice is not None:
            try:
                self._sapi_voice.Speak("", 2)
            except Exception as exc:
                logger.debug(f"SAPI purge error: {exc}")

        # 3. Purge pyttsx engine
        if self._pyttsx_engine is not None:
            try:
                self._pyttsx_engine.stop()
            except Exception as exc:
                logger.debug(f"pyttsx stop error: {exc}")

        self._is_speaking_flag.clear()
        self._event_bus.emit(Events.VOICE_SPEECH_END, text="")

    def purge(self) -> None:
        """Alias for stop_speaking()."""
        self.stop_speaking()

    def get_engine_type(self) -> str:
        """Return which underlying TTS engine was initialized."""
        return self._engine_type

    def _speech_worker(self) -> None:
        """Background thread that consumes utterances from the speech queue."""
        # Initialize COM in this thread for SAPI
        sapi_voice = None
        pyttsx_engine = None

        # Attempt 1: comtypes SAPI
        try:
            import comtypes
            import comtypes.client
            comtypes.CoInitialize()
            sapi_voice = comtypes.client.CreateObject("SAPI.SpVoice")
            sapi_voice.Rate = 1  # Moderate natural pace
            sapi_voice.Volume = int(config.TTS_VOLUME * 100)
            self._engine_type = "Windows SAPI (comtypes)"
            self._sapi_voice = sapi_voice
            logger.info("Initialized native Windows SAPI TTS via comtypes.")
        except Exception as sapi_err:
            logger.warning(f"Failed to initialize SAPI via comtypes: {sapi_err}")

        # Attempt 2: pywin32 win32com SAPI
        if sapi_voice is None:
            try:
                import win32com.client
                import pythoncom
                pythoncom.CoInitialize()
                sapi_voice = win32com.client.Dispatch("SAPI.SpVoice")
                sapi_voice.Rate = 1
                sapi_voice.Volume = int(config.TTS_VOLUME * 100)
                self._engine_type = "Windows SAPI (win32com)"
                self._sapi_voice = sapi_voice
                logger.info("Initialized native Windows SAPI TTS via win32com.")
            except Exception as win32_err:
                logger.warning(f"Failed to initialize SAPI via win32com: {win32_err}")

        # Attempt 3: pyttsx3 fallback
        if sapi_voice is None:
            try:
                import pyttsx3
                pyttsx_engine = pyttsx3.init()
                pyttsx_engine.setProperty("rate", config.TTS_RATE)
                pyttsx_engine.setProperty("volume", config.TTS_VOLUME)
                self._engine_type = "pyttsx3 Fallback"
                self._pyttsx_engine = pyttsx_engine
                logger.info("Initialized pyttsx3 TTS engine as fallback.")
            except Exception as pyttsx_err:
                logger.error(f"Failed to initialize pyttsx3 fallback: {pyttsx_err}")
                self._engine_type = "None (Audio synthesis unavailable)"

        while self._running:
            try:
                utterance = self._speech_queue.get(timeout=0.2)
            except queue.Empty:
                continue

            if utterance is None:
                break

            self._is_speaking_flag.set()
            self._event_bus.emit(Events.VOICE_SPEECH_START, text=utterance)

            try:
                if sapi_voice is not None:
                    # Async speak (flag 1) with fast poll so interrupt can purge immediately
                    sapi_voice.Speak(utterance, 1)
                    while self._is_speaking_flag.is_set() and self._running:
                        # WaitUntilDone with short timeout
                        done = sapi_voice.WaitUntilDone(50)
                        if done:
                            break
                elif pyttsx_engine is not None:
                    pyttsx_engine.say(utterance)
                    pyttsx_engine.runAndWait()
                else:
                    logger.warning(f"[MOCK TTS] {utterance}")
                    time.sleep(0.5)
            except Exception as speak_err:
                logger.error(f"Error during TTS synthesis: {speak_err}")
            finally:
                time.sleep(0.15)
                self._is_speaking_flag.clear()
                self._event_bus.emit(Events.VOICE_SPEECH_END, text=utterance)
                self._speech_queue.task_done()
                self._speech_queue.task_done()

        # Cleanup COM
        try:
            import comtypes
            comtypes.CoUninitialize()
        except Exception:
            pass

    def _speak_direct(self, text: str) -> None:
        """Synchronous speech for diagnostics or test routines."""
        self._is_speaking_flag.set()
        self._event_bus.emit(Events.VOICE_SPEECH_START, text=text)
        try:
            import comtypes
            import comtypes.client
            comtypes.CoInitialize()
            voice = comtypes.client.CreateObject("SAPI.SpVoice")
            voice.Rate = 1
            voice.Volume = int(config.TTS_VOLUME * 100)
            voice.Speak(text)
            comtypes.CoUninitialize()
        except Exception as exc:
            logger.warning(f"Direct SAPI speak error: {exc}. Trying pyttsx3 fallback.")
            try:
                import pyttsx3
                engine = pyttsx3.init()
                engine.say(text)
                engine.runAndWait()
            except Exception as pyttsx_exc:
                logger.error(f"Direct fallback speak error: {pyttsx_exc}")
        finally:
            time.sleep(0.2)
            self._is_speaking_flag.clear()
            self._event_bus.emit(Events.VOICE_SPEECH_END, text=text)
