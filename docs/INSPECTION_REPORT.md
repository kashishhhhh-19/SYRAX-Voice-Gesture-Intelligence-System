# SYRAX UPGRADE — PHASE 0 INSPECTION REPORT

**Date:** 2026-11-02
**System:** Windows 11 Laptop (x64)
**Target Environment:** Built-in Realtek HD Audio Mic + Built-in USB Webcam (Realtek VID_0BDA&PID_5830)
**Backup:** Verified at `<USERPROFILE>\OneDrive\Desktop\SYRAX_original_backup.zip` (175,605 bytes)

---

## 1. PROJECT ENVIRONMENT & TREE

### 1.1 Python Environment & Versions
- **Active System Python:** `Python 3.14.7` (`C:\Program Files\Python314\python.exe`)
- **Secondary Installed Python:** `Python 3.12.0` (`<USERPROFILE>\AppData\Local\Programs\Python\Python312\python.exe`)
- **Virtual Environment:** Present at `<USERPROFILE>\OneDrive\Desktop\SYRAX\.venv`
- **Installed Packages (`pip list` / `pip freeze` key highlights):**
  - `mediapipe == 1.1.1`
  - `opencv-python == 5.0.0.93`
  - `opencv-contrib-python == 5.0.0.93`
  - `PyAutoGUI == 0.9.54`
  - `pywin32 == 312` / `pypiwin32 == 223`
  - `sounddevice == 0.5.6`
  - `SpeechRecognition == 3.17.0`
  - `pyttsx3 == 2.99`
  - `pytest == 9.1.1`
  - `numpy == 2.5.2`
  - `pillow == 13.0.0`
  - `comtypes == 1.4.16`

### 1.2 Entry Point & Launch Mechanism
- **Entry Point:** `main.py`
  - Interactive GUI mode: `python main.py`
  - Subsystem Hardware Self-Test CLI: `python main.py --diagnose`
- **Launcher Script:** `launch_syrax.bat` (configures terminal encoding, activates environment if present, executes `python main.py`).

### 1.3 Project Tree
```
SYRAX/
├── actions/
│   ├── __init__.py
│   ├── browser_actions.py
│   ├── focus_manager.py
│   ├── instagram_actions.py
│   ├── media_actions.py
│   ├── presentation_actions.py
│   ├── whatsapp_actions.py
│   └── youtube_actions.py
├── core/
│   ├── __init__.py
│   ├── action_dispatcher.py
│   ├── application_controller.py
│   ├── assistant_engine.py
│   ├── browser_manager.py
│   ├── command_parser.py
│   ├── conversation_state.py
│   ├── entity_extractor.py
│   ├── event_bus.py
│   ├── focus_manager.py
│   ├── intent_classifier.py
│   ├── interrupt_manager.py
│   └── logger.py
├── docs/
│   ├── ARCHITECTURE.md
│   ├── INSPECTION_REPORT.md  <-- THIS FILE
│   └── ...
├── gesture/
│   ├── __init__.py
│   ├── gesture_actions.py
│   ├── gesture_classifier.py
│   ├── gesture_engine.py
│   └── gesture_profiles.py
├── GestureFlow/             <-- Copied from <USERPROFILE>\OneDrive\Documents\GESTURE FLOW
│   ├── app/
│   │   ├── camera.py
│   │   ├── config.py
│   │   ├── gesture_controller.py
│   │   ├── gesture_recognition.py
│   │   ├── hand_tracking.py
│   │   └── ui.py
│   ├── tests/
│   └── main.py
├── gui/
│   ├── __init__.py
│   ├── dashboard.py
│   └── widgets.py
├── logs/
│   └── syrax.log
├── tests/
│   ├── test_application_controller.py
│   ├── test_browser_manager.py
│   ├── test_command_parser.py
│   ├── test_entity_extractor.py
│   ├── test_focus_manager.py
│   ├── test_gesture_classifier.py
│   ├── test_gesture_profiles.py
│   ├── test_instagram_actions.py
│   ├── test_intent_classifier.py
│   ├── test_interrupt_manager.py
│   ├── test_whatsapp_actions.py
│   └── test_youtube_actions.py
├── voice/
│   ├── __init__.py
│   ├── tts_engine.py
│   └── voice_engine.py
├── config.py
├── main.py
└── requirements.txt
```

---

## 2. VOICE ENGINE ARCHITECTURE & PROTECTED FILES

### 2.1 Structure
- **Microphone & Speech-to-Text (`voice/voice_engine.py`):**
  - Uses `SpeechRecognition` (`sr.Recognizer`) with Google Web STT.
  - Automatically probes physical devices for built-in `"Realtek"` keywords (`config.PREFERRED_MIC_KEYWORD = "Realtek"`).
  - Implements custom `SoundDeviceMicrophone(sr.AudioSource)` fallback class when PyAudio native stream is absent.
  - Manages dynamic energy thresholds (`config.DYNAMIC_ENERGY_THRESHOLD = True`, damping 0.15, ratio 1.5).
  - Background daemon worker thread `_listen_loop()` non-blockingly streams audio frames.
  - Echo suppression: checks TTS speaking state to avoid picking up its own audio feedback.
- **Text-to-Speech (`voice/tts_engine.py`):**
  - Dual-engine priority: Windows SAPI5 primary with `pyttsx3` fallback.
  - Rate: 175 wpm, Volume: 1.0.
  - Thread-safe playback with instant purge/interrupt tokens.
- **Protected Files (Strict Non-Negotiable Rule 2):**
  - `voice/voice_engine.py` — **PROTECTED (Do not modify)**
  - `voice/tts_engine.py` — **PROTECTED (Do not modify)**
  - Any extensions must be external via new command intents, action dispatcher routing entries, or subscriber listeners on the EventBus.

---

## 3. COMMAND PARSING, ROUTING & APPLICATION LAUNCHERS

### 3.1 Command Parsing Pipeline (`core/command_parser.py`)
1. **Interrupt Check:** High-priority matches (`stop`, `cancel`, `exit`, `pause`) handled via `InterruptManager`.
2. **Multi-turn Confirmation:** If `ConversationState.has_pending_confirmation`, maps `yes`/`confirm` -> `CONFIRMATION(confirm)` or `no`/`cancel` -> `CONFIRMATION(cancel)`.
3. **Intent Classification & Entity Extraction:**
   - `core/intent_classifier.py`: Rule-based keyword & pattern classification supporting English, Hindi, and Hinglish.
   - `core/entity_extractor.py`: Extracts target apps, contact names, song titles, artists, search queries.
4. **Fuzzy Matching Fallback:** Levenshtein/difflib ratio against canonical phrases (`FUZZY_MATCH_CUTOFF = 0.75`).

### 3.2 Exact App URL Opening Locations
- **`actions/browser_actions.py`:**
  - `open_site(site_name)`: Looks up `config.QUICK_SITES`.
  - Line 51: Calls `cls.open_url(url, app_key=key)`.
  - Lines 31 & 39: Primary via `BrowserManager.open_tab(url)` (Chrome DevTools Protocol port 9222), fallback via standard `webbrowser.open_new_tab(url)`.
- **`config.py` (Lines 154–166):**
  - `"youtube": "https://www.youtube.com"`
  - `"google": "https://www.google.com"`
  - `"github": "https://www.github.com"`
  - `"instagram": "https://www.instagram.com"`
- **`actions/whatsapp_actions.py` (Line 43 & 58–100):**
  - Line 43: `WHATSAPP_URL = "https://web.whatsapp.com"`
  - Line 66: Opens via `browser_manager.open_tab(self.WHATSAPP_URL, app_key="whatsapp")`
  - Line 93: Fallback via `webbrowser.open_new_tab(self.WHATSAPP_URL)`
  - **FINDING:** WhatsApp Web URL is hardcoded here and in `config.QUICK_SITES`. There is currently **zero native desktop app discovery** for WhatsApp.
- **`actions/youtube_actions.py` (Lines 133, 256, 267, 283, 299):**
  - Opens `https://www.youtube.com/watch?v=...` or `https://www.youtube.com/results?search_query=...` via browser CDP or `webbrowser.open_new_tab()`.
  - **FINDING:** There is currently **no desktop/PWA discovery or launching** for YouTube.

---

## 4. TKINTER DASHBOARD STRUCTURE

### 4.1 Framework & Architecture (`gui/dashboard.py`)
- **Root Window:** Tkinter `tk.Tk()`, geometry `1180x760`, dark cyberpunk theme.
- **Colors & Styling (`config.py`):**
  - Dark background: `#080c14`, Cards: `#0f172a`, Panels: `#131e33`, Input: `#1a243b`
  - Neon Cyan (`#00f0ff`), Blue (`#0088ff`), Green (`#00ff88`), Red (`#ff3366`), Yellow (`#ffbb00`), Purple (`#b026ff`)
  - Fonts: `Segoe UI` (Primary), `Consolas` (Monospace telemetry)
- **Threading Model:**
  - Background engines (Voice, Gesture, Diagnostics) run in isolated Python daemon threads.
  - **Thread-Safety:** Background events emit to `core/event_bus.py`, which enqueues payloads to `self._ui_queue: queue.Queue`.
  - Periodic polling mechanism: `self.root.after(30, self._process_ui_queue)` safely pulls from queue and mutates widgets exclusively on the Tkinter main thread.
- **Existing Layout Cards:**
  - **Hero Card (Top):** AI animated waveform visualizer, spoken text response display, pending-message confirmation frame (`SEND` / `CANCEL`), command input entry bar.
  - **Voice Intelligence Card (Left-Mid):** Mic toggle button (`MIC ON/OFF`), status pill (`LISTENING`), noise calibration button, recognized speech text, input mic device selector.
  - **Gesture Intelligence Card (Left-Bot):** Camera toggle button (`CAM ON/OFF`), hand detected pill, mode pill (`IDLE/ACTIVE`), camera preview canvas (220x140), current gesture readout, control cheat-sheet.
  - **System Status Card (Right-Top):** Telemetry pills for Voice Engine, Vision Tracker, Internet STT, YouTube Focus, Active App Context, WhatsApp status, Instagram status, Browser CDP, Run Diagnostics button.
  - **Activity History Card (Right-Bot):** Scrollable text stream of timestamped events.

---

## 5. EXISTING GESTURE ENGINES: SYRAX vs GESTUREFLOW

| Feature / Subsystem | SYRAX Existing Implementation (`gesture/`) | GestureFlow Implementation (`GestureFlow/app/`) | Comparison & Strongest Parts |
|---|---|---|---|
| **Camera Management** | Integrated directly inside `GestureEngine._capture_loop()`. Uses `cv2.VideoCapture(0, cv2.CAP_DSHOW)`. Fixed sleep intervals. No reconnection backoff or device name. | Separate `CameraStream` in `app/camera.py`. Background grab thread with FPS calculation, lock protection, and error flags. | **GestureFlow** has better thread separation in camera capture; SYRAX has direct event bus integration. Merged CameraManager will combine both with automatic reconnection. |
| **Detection Backend** | Legacy `mp.solutions.hands` check. Fails on Python 3.14/MediaPipe 1.1.1 and falls back to rudimentary skin-color segmentation (`cv2.inRange`) + contour convex hull. | Legacy `mp.solutions.hands` check in `app/hand_tracking.py`. Also fails on Python 3.14/MediaPipe 1.1.1 without fallback. | **Neither** currently works with modern MediaPipe Tasks API (`vision.HandLandmarker`). We must build the Tasks `HandLandmarker` backend while keeping OpenCV as fallback. |
| **Landmark Normalization** | Raw normalized `(x, y)` from MediaPipe or synthesized from OpenCV contour. Simple rolling average smoothing (`deque(maxlen=5)`). | Rich `HandData` dataclass with `LandmarkPoint` (x, y, z, px, py), bounding box, palm center (wrist + 4 knuckle bases average), scale normalization (`wrist -> middle MCP`). | **GestureFlow is significantly stronger** in geometric feature normalization (rotation-tolerant distance scaling). |
| **Static Pose Classification** | `gesture/gesture_classifier.py`: `is_fist`, `is_open_palm`, `is_two_fingers`, `is_one_finger`, `is_pinch`. Relies heavily on inverted Y-coordinates (`tip[1] < pip[1]`). | `GestureFlow/app/gesture_recognition.py`: `_get_finger_extensions` uses Euclidean distance ratio `dist_tip_mcp / dist_pip_mcp >= 1.60` (rotation-invariant). | **GestureFlow is far superior** for static finger extension; SYRAX has better pose coverage (`TWO_FINGERS`, `PINCH`). Merged classifier will use scale-normalized Euclidean ratios. |
| **Dynamic Motion Tracking** | Centroid history buffer tracks `WRIST` coordinates. Swipe requires `abs(vx) > SWIPE_VELOCITY_THRESHOLD * 8`. | `MotionHistory` tracks palm center `(cx, cy)` and pinch distance. Computes `(dx, dy, vx, vy)` over sliding window. Requires `dx >= min_displacement` AND `vx >= min_velocity` AND `dy` drift bounds. | **GestureFlow motion detection is far stronger and cleaner**. SYRAX's wrist tracking causes severe motion jitter. |
| **Debounce & Cooldown** | Global per-gesture timestamp dictionary in `GestureClassifier`. | Individual cooldowns + global cooldown in `GestureRecognizer`. Frame stability counter (`stability_required_frames = 3`) before static poses confirm. | **GestureFlow's stability counter** prevents single-frame noise from firing. SYRAX's per-gesture cooldowns prevent re-triggers. Merged state machine will use both. |
| **Action Execution & Focus** | Enforces `FocusManager.execute_youtube_action` for media and scrolling. Focus check is locked to YouTube window title. | Mode-based (`PRESENTATION`, `SCROLLING`, `UNIFIED`). Direct `pyautogui` calls. No foreground window focus verification. | **SYRAX has the focus safety concept**, but it was hardcoded to YouTube; GestureFlow has clean mode execution. Merged system needs profile-based focus validation. |

---

## 6. ROOT-CAUSE ANALYSIS OF THE BROKEN SCROLLING

We systematically audited every potential failure mechanism for scrolling in both codebases:

1. **Wrong Landmark Indices: APPLIES (CRITICAL)**
   - **SYRAX (`gesture/gesture_classifier.py` Lines 292–294, 301–306):**
     `cx, cy = wrist[0], wrist[1]`
     Velocity `vy` used for scrolling was derived from `WRIST` (landmark 0), NOT from the index fingertip (`INDEX_TIP`, landmark 8)! When the user points and moves their finger to scroll, the wrist is mostly stationary.
   - **GestureFlow (`app/gesture_recognition.py` Lines 306–326):**
     GestureFlow checks the vector from `INDEX_FINGER_MCP` to `INDEX_FINGER_TIP` to determine `POINTING_UP` vs `POINTING_DOWN`, which works, but relies on static posture rather than continuous displacement.

2. **Wrong Finger Counting: APPLIES (MODERATE)**
   - **SYRAX (`gesture/gesture_classifier.py` Lines 92–93):**
     `y_extended = tip[1] < (pip[1] - 0.015)`
     In inverted screen coordinates, `tip[1] < pip[1]` only works when the hand is held strictly upright. If the hand tilts forward or downward toward the camera, this check evaluates to `False`, losing the `ONE_FINGER` classification entirely.

3. **Thresholds Too Small or Too Large: APPLIES (CRITICAL)**
   - **SYRAX (`gesture/gesture_classifier.py` Line 458):**
     Requires `abs(vy) > 0.15` on the wrist! In normalized screen units, 0.15/s requires moving 15% of the total webcam frame height every second. Because the wrist barely moves during finger scrolling, this threshold was almost never crossed reliably.
   - Conversely, when it did cross, a fixed discrete `SCROLL_STEP = 240` was emitted every 140ms (`SCROLL_REPEAT_INTERVAL = 0.14`), resulting in jumpy, stuttering bursts rather than smooth scrolling.

4. **Mirrored Camera / Flipped X-Axis & Handedness: APPLIES (MODERATE)**
   - **SYRAX (`gesture/gesture_engine.py` Line 197):**
     `frame = cv2.flip(frame, 1)` mirrors the frame before passing to landmark extraction. On mirrored frames, MediaPipe's Left hand is classified as Right and vice-versa. There was no central correction for handedness or X-axis directionality.

5. **Normalized vs Pixel Coordinates: APPLIES (MINOR)**
   - In SYRAX, scroll amounts were fixed magic integers (`SCROLL_STEP = 240`) sent to `pyautogui.scroll()`, completely disconnected from the actual spatial displacement or velocity of the user's hand.

6. **Missing Cooldown / Repeated Triggers While Hand is Static: APPLIES (CRITICAL)**
   - **GestureFlow (`app/gesture_recognition.py` Lines 380–383):**
     ```python
     if not on_cooldown and (confirmed_gesture != self._last_active_gesture or raw_gesture in (GestureType.POINTING_UP, GestureType.POINTING_DOWN)):
         should_trigger = True
     ```
     `POINTING_UP` and `POINTING_DOWN` explicitly BYPASSED the release check! As long as the user held their finger up statically, it fired scroll actions continuously every 0.25 seconds.
   - Scrolling must be **motion/displacement-driven**, not pose-driven. A stationary pointing finger must produce **zero** scroll events!

7. **Wrong Window Focus When Sending Keys: APPLIES (FATAL BUG)**
   - **SYRAX (`actions/presentation_actions.py` Lines 81–94):**
     ```python
     @staticmethod
     def scroll(direction: str, amount: int = config.SCROLL_STEP) -> Tuple[bool, str]:
         focus_mgr = get_focus_manager()
         delta = amount if direction.lower() == "up" else -amount
         def _action():
             pyautogui.scroll(delta)
             return True, f"Scrolled {direction}."
         return focus_mgr.execute_youtube_action(_action, needs_player_click=False)
     ```
     `PresentationActions.scroll()` explicitly wrapped the scroll inside `focus_mgr.execute_youtube_action()`!
     If YouTube was not the foreground window (e.g. if the user was on Instagram, WhatsApp, PowerPoint, a PDF, or any browser tab other than YouTube), `execute_youtube_action()` aborted and returned `(False, "Please open YouTube first.")`!
     **This meant scrolling in any application other than YouTube was completely blocked by design.**

---

## 7. BASELINE TEST SUITE RESULTS (BEFORE ANY MODIFICATION)

### 7.1 SYRAX Test Suite
- **Command:** `python -m pytest tests/ -v` (on Python 3.14.7)
- **Result:** **88 PASSED, 0 FAILED** in 2.56s
  - `test_application_controller.py`: 5 passed
  - `test_browser_manager.py`: 5 passed
  - `test_command_parser.py`: 13 passed
  - `test_entity_extractor.py`: 8 passed
  - `test_focus_manager.py`: 7 passed
  - `test_gesture_classifier.py`: 12 passed
  - `test_gesture_profiles.py`: 5 passed
  - `test_instagram_actions.py`: 7 passed
  - `test_intent_classifier.py`: 7 passed
  - `test_interrupt_manager.py`: 5 passed
  - `test_whatsapp_actions.py`: 7 passed
  - `test_youtube_actions.py`: 7 passed
- **Note on Python 3.12 compatibility:** When running pytest under Python 3.12, `core/interrupt_manager.py:63` failed collection because `Any` was used in `def __init__(self, tts_engine: Optional[Any] = None)` without being imported from `typing`. Python 3.14's deferred annotation evaluation allowed it to pass, but `from typing import Any` is needed for universal compatibility.

### 7.2 GestureFlow Test Suite
- **Command:** `python -m pytest GestureFlow/tests/ -v` (on Python 3.14.7)
- **Result:** **30 PASSED, 0 FAILED** in 1.20s
  - `test_gesture_controller.py`: 12 passed
  - `test_gesture_recognition.py`: 18 passed

---

## 8. HARDWARE & MEDIAPIPE AUDIT (REAL ENVIRONMENT EVIDENCE)

### 8.1 MediaPipe Version & API Exposure
- **Installed MediaPipe Version:** `mediapipe 1.1.1` on Python 3.14.7
- **`hasattr(mp, "solutions")`:** `False`
  - The legacy `mp.solutions.hands` API **does not exist** in MediaPipe 1.1.1 on Python 3.14.
  - Any code calling `mp.solutions.hands` raises `AttributeError: module 'mediapipe' has no attribute 'solutions'`.
- **`hasattr(mp, "tasks")`:** `True`
  - Exposes `mediapipe.tasks.python.vision.HandLandmarker` and `mediapipe.tasks.python.vision.GestureRecognizer`.
- **Model Task Bundle Audit:**
  - Located model bundle at `<USERPROFILE>\OneDrive\Desktop\ZENYX\gesture_recognizer.task` (8,373,440 bytes).
  - Inspected archive structure via Python `zipfile`: Contains `hand_landmarker.task` (`hand_detector.tflite` + `hand_landmarks_detector.tflite`) and `hand_gesture_recognizer.task`.
  - Verified runtime: `vision.GestureRecognizer.create_from_options()` and `vision.HandLandmarker.create_from_options()` instantiate and run inferences successfully on CPU using TensorFlow Lite XNNPACK delegate.

### 8.2 Camera Enumeration
- **PowerShell `Get-PnpDevice -Class Camera`:**
  - Device Name: `USB camera`
  - Hardware ID: `USB\VID_0BDA&PID_5830&MI_00\6&84045DC&0&0000` (Built-in Realtek Semiconductor webcam)
  - Status: `OK`
- **OpenCV Capture Verification:**
  - Index 0 opens with `cv2.CAP_DSHOW`.
  - Captures valid frames at resolution `1280x720x3`.
  - Releases cleanly with zero camera leaks.

### 8.3 WhatsApp Desktop Detection Audit
- **Package Audit (`Get-AppxPackage *WhatsApp*`):**
  - Name: `5319275A.WhatsAppDesktop`
  - PackageFamilyName: `5319275A.WhatsAppDesktop_cv1g1gvanyjgm`
  - InstallLocation: `C:\Program Files\WindowsApps\5319275A.WhatsAppDesktop_2.2443.5.0_x64__cv1g1gvanyjgm`
- **Start Apps Audit (`Get-StartApps`):**
  - Name: `WhatsApp`
  - AppUserModelID (AUMID): `5319275A.WhatsAppDesktop_cv1g1gvanyjgm!App`
  - Launchable via: `explorer.exe shell:AppsFolder\5319275A.WhatsAppDesktop_cv1g1gvanyjgm!App`
- **FINDING:** Native WhatsApp Desktop is **installed and verified** on this laptop!

### 8.4 YouTube Desktop / PWA Audit
- **Start Apps Audit (`Get-StartApps`):**
  - Found Chrome PWA: `YouTube`
  - AppUserModelID: `Chrome._crx_agimnkijcamfeangaknmldooml`
  - Launchable via: `explorer.exe shell:AppsFolder\Chrome._crx_agimnkijcamfeangaknmldooml`
- **FINDING:** A native YouTube Chrome PWA is **installed and verified** on this laptop!

---

## 9. CONCLUSION & ARCHITECTURAL UPGRADE ROADMAP

All baseline tests pass. The root causes of the broken scrolling have been identified and traced to specific files and lines. MediaPipe Tasks and hardware devices have been empirically verified. We are ready to proceed with Phase 1.
