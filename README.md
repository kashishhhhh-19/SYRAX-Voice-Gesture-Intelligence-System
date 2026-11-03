# SYRAX: Voice & Gesture Intelligence System

> **"Speak. Gesture. Control."**
>
> An AI-powered desktop assistant combining voice recognition and hand gesture control for seamless, hands-free computer interaction on Windows 10/11.

[![Python Version](https://img.shields.io/badge/Python-3.10%2B%20%7C%203.14-blue.svg)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/Platform-Windows%2010%20%7C%2011-0078D6.svg)](https://www.microsoft.com/windows)
[![UI Theme](https://img.shields.io/badge/Interface-Cyberpunk%20Neon-00f0ff.svg)](https://docs.python.org/3/library/tkinter.html)
[![Repository](https://img.shields.io/badge/GitHub-SYRAX-181717.svg?logo=github)](https://github.com/kashishhhhh-19/SYRAX-Voice-Gesture-Intelligence-System)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**SYRAX** is an AI-powered desktop intelligence assistant engineered for Windows 10/11. It allows complete, hands-free laptop navigation using natural spoken commands and intuitive hand gestures—dramatically reducing dependence on traditional keyboard and mouse input.

Controlled through a futuristic sci-fi dashboard, SYRAX continuously monitors voice and spatial hand movements, executes browser, media, and presentation automations, and speaks back with zero audio loopback interference.

---

## Table of Contents
1. [Core Priorities & Architecture](#core-priorities--architecture)
2. [Tech Stack](#tech-stack)
3. [Setup & First-Run Guide](#setup--first-run-guide)
   - [Automated Setup (setup.bat)](#automated-setup-setupbat)
   - [PyAudio-First Installation (Critical Windows Step)](#pyaudio-first-installation-critical-windows-step)
   - [Automatic SoundDevice Fallback](#automatic-sounddevice-fallback)
4. [Diagnostics Mode (`--diagnose`)](#diagnostics-mode---diagnose)
5. [Voice Intelligence Reference](#voice-intelligence-reference)
6. [Gesture Intelligence Reference (GestureFlow)](#gesture-intelligence-reference-gestureflow)
7. [Futuristic Dashboard Overview](#futuristic-dashboard-overview)
8. [Troubleshooting](#troubleshooting)
9. [Future Extension Points](#future-extension-points)

---

## Core Priorities & Architecture

SYRAX is designed around four strict engineering priorities:
1. **Voice Recognition Reliability (Top Priority)**: Zero dropped sessions, built-in Realtek laptop mic optimization without requiring headphones, intelligent dynamic ambient noise calibration, and automatic mic-muting during TTS speech output to prevent self-triggering audio loops.
2. **Gesture Control Reliability**: Rolling-window coordinate smoothing, velocity-based swipe detection, cooldown debounce gating, and an explicit state machine (`IDLE` -> `ACTIVE` -> `EXIT`) requiring a **Fist** gesture to engage commands.
3. **Dashboard Polish**: Responsive dark cyberpunk aesthetic (`#080c14`, `#00f0ff`, `#0088ff`), real-time sinusoidal multi-harmonic canvas waveform, live camera feed with HUD reticle overlay, and thread-safe queue updates.
4. **Extras & Modularity**: Multi-source command parsing (Voice + Text + Gestures), unified action dispatcher, and clear extension points for offline STT and LLMs.

### System Architecture Flow
```
+-----------------------------------------------------------------------------------+
|                                 SYRAX DASHBOARD                                   |
|   (Animated Waveform | Live HUD Camera Preview | Status Telemetry | Activity Log) |
+-----------------------------------------+-----------------------------------------+
                                          |
                                    Event Bus (Decoupled, Thread-Safe)
                                          |
                        +-----------------+-----------------+
                        |                                   |
              [ Voice Engine ]                    [ Gesture Engine ]
         (Realtek Mic / PyAudio /              (Webcam / MediaPipe Hands /
             sounddevice Fallback)                 OpenCV Adaptive Pipeline)
                        |                                   |
                        v                                   v
             [ Command Parser ]                    [ Gesture Actions ]
       (Rules + Regex + Fuzzy Difflib)          (State Machine + Cooldowns)
                        |                                   |
                        +-----------------+-----------------+
                                          |
                                [ Action Dispatcher ]
                                          |
           +------------------------------+------------------------------+
           |                              |                              |
    [ Browser Actions ]           [ Media Actions ]            [ Presentation Actions ]
  (YouTube, Google, Sites)     (Play/Pause, Seek, Vol)           (Slides, Zoom, Scroll)
           |                              |                              |
           +------------------------------+------------------------------+
                                          |
                              [ Spoken TTS Output ]
                       (Windows SAPI via comtypes / win32com)
                           *Listening is paused during TTS*
```

---

## Tech Stack

- **Operating System**: Windows 10 / 11
- **Runtime**: Python 3.10+
- **Control GUI**: Tkinter (Dark theme, neon cyan/blue `#00f0ff` accents, canvas-rendered animated sinusoidal waveform)
- **Speech Recognition**: `SpeechRecognition` + Google Speech Recognition API (`recognize_google`)
- **Microphone Capture**: `PyAudio` (with automatic seamless fallback to `sounddevice` if PyAudio is absent)
- **Text-to-Speech (TTS)**: Native Windows SAPI via `comtypes` / `win32com.client` (with `pyttsx3` fallback)
- **Vision & Hand Tracking**: MediaPipe Hands + OpenCV + adaptive skin-contour tracker fallback
- **Browser Automation Layer**: Chrome DevTools Protocol (CDP via Playwright `connect_over_cdp`) with persistent profile directory (`%LOCALAPPDATA%\SYRAX\browser_profile`)
- **OS Fallback Automation**: Windows Win32 API (`pywin32`) + `pyautogui`, `webbrowser`, `urllib.parse`
- **Concurrency**: `threading` + `queue.Queue` (Tkinter mainloop is never blocked; all updates poll via `root.after()`)

---

## Setup & First-Run Guide

### Cloning & Setup

#### 1. Clone the Repository
```cmd
git clone https://github.com/kashishhhhh-19/SYRAX-Voice-Gesture-Intelligence-System.git
cd SYRAX-Voice-Gesture-Intelligence-System
```

#### 2. Automated Setup (`setup.bat`)
The fastest way to install and verify SYRAX on Windows is to run the automated setup script:
```cmd
setup.bat
```
`setup.bat` performs the following steps automatically:
1. Verifies that Python 3.10+ is installed and present in your system PATH.
2. Creates and activates an isolated virtual environment (`.venv`).
3. **Installs PyAudio FIRST** using multi-tier installation logic.
4. Installs the remaining dependencies from `requirements.txt`.
5. Automatically runs `python main.py --diagnose` to confirm every subsystem is healthy.

---

### PyAudio-First Installation (Critical Windows Step)

On Windows, `pip install pyaudio` is the most common point of failure because PyAudio requires C++ compilation against the PortAudio C library.

#### Installation Order:
```cmd
# 1. Install PyAudio FIRST
pip install pyaudio

# 2. If direct install fails (missing C++ compiler), try pipwin:
pip install pipwin
pipwin install pyaudio

# 3. If pipwin fails, download the pre-compiled wheel matching your Python version:
#    (e.g., PyAudio-0.2.14-cp311-cp311-win_amd64.whl from Unofficial Windows Binaries)
pip install <wheel_file_name>.whl

# 4. Once PyAudio is installed (or skipped for sounddevice fallback), install requirements:
pip install -r requirements.txt
```

---

### Automatic SoundDevice Fallback

If PyAudio cannot be installed on your machine, **SYRAX will NOT crash**.

SYRAX features an internal `SoundDeviceMicrophone` adapter class that implements the `speech_recognition.AudioSource` interface using `sounddevice.RawInputStream`. It automatically captures 16-bit PCM microphone streams from your Realtek laptop mic and feeds them directly into Google Speech Recognition without requiring PyAudio at all.

---

---

## Automated Test Suite

SYRAX comes with a comprehensive suite of 118 unit and integration tests covering intent classification, focus management, gesture kinetics, and controller safety:

```cmd
# Run core SYRAX test suite (88 tests)
pytest tests -v

# Run GestureFlow test suite (30 tests)
pytest GestureFlow/tests -v
```

All tests run deterministically with pure mathematical landmark vectors without requiring a physical camera or microphone.

## Diagnostics Mode (`--diagnose`)

Before running SYRAX or whenever troubleshooting audio/camera issues, run the comprehensive diagnostics test:

```cmd
python main.py --diagnose
```

### What It Tests:
1. **Microphone**: Probes input devices, auto-binds Realtek mic, and measures RMS energy level.
2. **Speech Recognition (STT)**: Tests network connectivity to the Google Speech Recognition service.
3. **Text-to-Speech (TTS)**: Tests Windows SAPI voice synthesizer.
4. **Webcam & Gestures**: Opens camera index 0, verifies resolution, and tests hand tracker.
5. **Desktop Automation**: Verifies PyAutoGUI screen coordinates and display driver injection.

If any test fails, it prints a clear, actionable **FIX HINT**.

> **Note**: You can also click the **RUN DIAGNOSTICS** button on the Dashboard at any time to run this self-test live and view the results in the Activity History pane.

---

## Voice Intelligence Reference

On startup, SYRAX delivers an audio greeting:
> *"Hello! I'm SYRAX. What would you like me to do?"*

The microphone activates, dynamically samples room noise for 1.0 second, and begins listening.

### Voice Commands Table

| Category | Spoken Phrases (Natural Variations) | Executed Action |
| :--- | :--- | :--- |
| **Greeting** | *"Hello SYRAX"*, *"Hi SYRAX"*, *"Hey"* | Greets back with personality response |
| **Web Sites** | *"Open YouTube"*, *"Launch Google"*, *"Go to GitHub"*, *"Open Instagram"*, *"Open Reddit"*, *"Open LinkedIn"*, *"Open ChatGPT"* | Opens requested site in system browser |
| **Web Search** | *"Search <query>"*, *"Google <query>"*, *"Look up <query>"*, *"Find <query>"* | Executes Google web search |
| **YouTube** | *"Play <query>"* (e.g. *"Play Python tutorial"*, *"Play Lo-Fi hip hop"*) | Opens YouTube search results for query |
| **Media Pause** | *"Pause"*, *"Pause video"*, *"Pause music"*, *"Stop playback"*, *"Freeze video"* | Sends `k` / `space` to pause playback |
| **Media Resume**| *"Play music"*, *"Resume video"*, *"Continue playback"*, *"Unpause"* | Resumes active media stream |
| **Media Track** | *"Next video"*, *"Next track"*, *"Skip"* | Skips to next video (`Shift + N`) |
| **Media Track** | *"Previous video"*, *"Previous track"*, *"Go back"* | Returns to previous video (`Shift + P`) |
| **Seek / Scrub**| *"Forward"*, *"Fast forward"*, *"Skip forward"* | Jumps forward 10 seconds (`l`) |
| **Seek / Scrub**| *"Rewind"*, *"Go back 10 seconds"* | Rewinds 10 seconds (`j`) |
| **Volume** | *"Volume up"*, *"Louder"*, *"Turn it up"* | Increases Windows master volume |
| **Volume** | *"Volume down"*, *"Quieter"*, *"Lower volume"* | Decreases Windows master volume |
| **Volume** | *"Mute"*, *"Unmute"*, *"Silence"* | Toggles Windows audio mute |
| **Gesture Mode**| *"Start gesture mode"*, *"Activate gesture mode"*, *"Gesture mode on"*, *"Stop gesture mode"*, *"Exit gesture mode"*, *"Gesture mode off"* | Toggles YouTube Gesture Mode ON / OFF |
| **Diagnostics** | *"Run diagnostics"*, *"Self test"*, *"Diagnose system"* | Runs subsystem diagnostic self-test |
| **Shutdown** | *"Close assistant"*, *"Exit SYRAX"*, *"Shutdown"* | Says goodbye and closes cleanly |

*If an unrecognized command is spoken, SYRAX responds: "Sorry, I didn't understand that."*

---

## YouTube Gesture Intelligence Reference

SYRAX features full hands-free **YouTube Gesture Control** when Gesture Mode is active. Gesture Mode can be engaged in three convenient ways:
1. **Hold a Fist for ~1.0 second** in front of the camera (toggles Gesture Mode ON/OFF).
2. **Spoken voice command**: *"start gesture mode"* / *"stop gesture mode"*, *"gesture mode on"* / *"gesture mode off"*.
3. **Dashboard Toggle**: Click the **GESTURE MODE** button in Section C.

> **Safety Gate**: All YouTube gestures are ignored while Gesture Mode is **OFF** (`IDLE`), preventing accidental inputs while typing or talking.

### YouTube Gesture Actions Table

| Category | Hand Gesture | Trigger Conditions | Executed YouTube / Browser Action | Spoken TTS Feedback |
| :--- | :--- | :--- | :--- | :--- |
| **Mode Toggle** | **Fist** | Held steady for ~1.0 s | Toggles Gesture Mode (`IDLE` <-> `ACTIVE`) | *"Gesture control active."* / *"Gesture control paused."* |
| **Playback** | **Open Palm** | Held steady for ~0.5 s (not moving fast) | **Play / Pause** current video (sends `k`) | *"Playback paused."* / *"Playback resumed."* |
| **Track Skip** | **Swipe Right** | Fast hand motion to the right | **Next Video** (`Shift + N`) | *"Next video."* |
| **Track Skip** | **Swipe Left** | Fast hand motion to the left | **Previous Video** (`Shift + P`, fallback `Alt + Left`) | *"Previous video."* |
| **Seek / Scrub** | **Two Fingers Moving Right** | Index + Middle extended, moving right | **Fast Forward 10s** (`l`) | *"Forwarding."* |
| **Seek / Scrub** | **Two Fingers Moving Left** | Index + Middle extended, moving left | **Rewind 10s** (`j`) | *"Rewinding."* |
| **Page Scroll** | **One Finger Moving Up** | Index extended only, hand moving upward | **Scroll Down Page** (`wheel down`) | *(Silent continuous action)* |
| **Page Scroll** | **One Finger Moving Down** | Index extended only, hand moving downward | **Scroll Up Page** (`wheel up`) | *(Silent continuous action)* |
| **Page Zoom** | **Pinch Out** | Thumb + Index distance increasing | **Zoom In** (`Ctrl + Plus`) | *"Zooming in."* |
| **Page Zoom** | **Pinch In** | Thumb + Index distance decreasing | **Zoom Out** (`Ctrl + Minus`) | *"Zooming out."* |

### Gesture Reliability & Announcer Controls
- **Pure Landmark Classification**: Static poses and kinematics are calculated via pure functions in `gesture/gesture_classifier.py`, enabling 100% deterministic unit testing without a physical webcam.
- **Swipe vs. Open Palm Separation**: An Open Palm will **never** trigger Play/Pause if the hand is moving fast (speed > threshold is classified as a swipe).
- **Temporal Smoothing & Debounce**: Rolling window majority vote over consecutive frames filters jitter. Dedicated per-gesture cooldown timers prevent repeated accidental executions.
- **Live HUD & Confidence**: Detected gesture name, confidence score (e.g. `94%`), and hold duration are displayed in real time on the dashboard and logged in the activity history.
- **Voice Feedback Controls**: SAPI TTS announcements provide brief audible confirmations. Voice announcements are throttled (no repeats within 2 seconds, and strictly silenced for continuous scroll). Voice feedback can be toggled ON/OFF live from the dashboard (**VOICE ANNOUNCE** button) or via `GESTURE_VOICE_FEEDBACK_ENABLED` in `config.py`. The microphone is always muted while speaking so SYRAX never hears itself.

---

## YouTube Browser Focus Management

To eliminate the frustrating issue of keyboard shortcuts being sent to the wrong window or the assistant dashboard itself, SYRAX implements an intelligent **Browser Focus Manager** (`actions/focus_manager.py`).

Every YouTube keyboard shortcut—whether triggered by a hand gesture or a voice command—is routed through this focus pipeline:

```
[ Gesture / Voice Trigger ]
             │
             ▼
1. Detect YouTube Browser Window
   Enumerate top-level windows; matches title keyword "YouTube" across
   Google Chrome, Microsoft Edge, Mozilla Firefox, Brave, Opera, Vivaldi.
   Ignores the SYRAX dashboard itself.
             │
             ├── If NOT found ──► Display & Speak: "Please open YouTube first." (Throttled)
             │                    Abort action. Never send blind shortcuts.
             ▼
2. Bring YouTube Window to Foreground
   Restores window if minimized (SW_RESTORE).
   Bypasses Windows SetForegroundWindow restrictions (Alt key pulse & AttachThreadInput).
   Verifies active foreground window via GetForegroundWindow with configurable retries.
             │
             ▼
3. Ensure Video Player / Tab Focus (Click Safety)
   Uses configurable click modes from config.py:
   - "safe_area" (Default): Clicks a neutral spot below the video player (50% W, 78% H),
     focusing the tab WITHOUT accidentally toggling video playback.
   - "player_center": Clicks the video center (50% W, 45% H) and tracks play state.
   Focus caching (FOCUS_CACHE_SECONDS = 2.0s) avoids duplicate clicks on rapid commands.
             │
             ▼
4. Pre-Flight Re-Verification
   Immediately before PyAutoGUI sends the shortcut key, verifies GetForegroundWindow
   is STILL the YouTube window. If focus was lost, aborts action and logs warning.
             │
             ▼
5. Execute Keyboard Shortcut
   Sends exact YouTube key (k, Shift+N, Shift+P, l, j, Ctrl+Plus/Minus, Scroll).
```

### Dashboard Focus Telemetry
Section D on the dashboard features a dedicated **YouTube Focus Pill**:
- `YOUTUBE FOCUSED` (Neon Green): Active YouTube browser window is confirmed in the foreground.
- `YOUTUBE DETECTED` (Neon Cyan): YouTube browser is open in background.
- `SWITCHING FOCUS` (Neon Yellow): Actively foregrounding and clicking into the browser.
- `YOUTUBE NOT FOUND` (Dim Slate): No browser running YouTube detected.

---

## Futuristic Dashboard Overview

The dashboard is structured into five cohesive sections:

- **Section A: Central AI Assistant (Hero Banner)**
  - Sci-fi SYRAX logo and tagline
  - Canvas-based sinusoidal animated waveform (pulses cyan when listening, shifts to harmonic green/purple when speaking, dims when mic is muted)
  - Spoken response text readout
  - Command input box + "Execute" button (enables testing all commands without speaking into the mic)
- **Section B: Voice Intelligence**
  - Instant Mic ON/OFF toggle
  - Live status indicator (`IDLE`, `CALIBRATING`, `LISTENING`, `PROCESSING`, `SPEAKING`, `ERROR`)
  - Recognized transcript display
  - Dropdown combobox to switch between audio input microphones live
  - "Calibrate Noise" button for on-demand room noise re-tuning
- **Section C: Gesture Intelligence**
  - Camera ON/OFF toggle
  - Hand detected pill (`YES` / `NO`)
  - Mode indicator pill (`IDLE` / `ACTIVE`)
  - Recognized gesture display
  - Live 240x160 camera preview canvas with skeletal joint connections and cyberpunk HUD reticle
- **Section D: System Status & Telemetry**
  - Voice Engine backend status (`ACTIVE` or `FALLBACK: sounddevice`)
  - Vision tracker status
  - Periodic internet ping monitor (`CONNECTED` / `DISCONNECTED`)
  - Last executed command indicator
  - "Run Diagnostics" button
- **Section E: Activity History**
  - Real-time scrollable, timestamped event log
  - Color-coded category tags: `[VOICE]`, `[GESTURE]`, `[ACTION]`, `[SYSTEM]`, `[ERROR]`, `[DIAG]`
  - "Clear" button to wipe the log

---

## Troubleshooting

### 1. Microphone not working or recognition failing
> **First Step**: Open terminal and run:
> ```cmd
> python main.py --diagnose
> ```
- **No input devices found**: Open Windows Settings -> Sound -> Input, and verify that your built-in microphone (e.g. Realtek Audio) is enabled and set as default.
- **Microphone permission blocked**: Open Windows Settings -> Privacy & Security -> Microphone, and ensure "Let desktop apps access your microphone" is set to **ON**.
- **PyAudio failed to install**: SYRAX will automatically use `sounddevice`. Check that `sounddevice` is installed (`pip install sounddevice`).

### 2. Camera cannot be opened
- Check if another application (Zoom, Microsoft Teams, Discord, or browser tab) is currently using your webcam.
- In Windows Settings -> Privacy & Security -> Camera, ensure desktop app access is enabled.
- If your laptop has multiple cameras, change `CAMERA_INDEX = 1` in `config.py`.

### 3. Speech Recognition says "Speech service unreachable"
- Google Speech Recognition requires an internet connection. Verify that your laptop has Wi-Fi or Ethernet internet access.

### 4. YouTube Shortcuts or Gestures not registering
- Ensure a browser window (Chrome, Edge, Firefox, Brave) has YouTube open. If YouTube is not detected, SYRAX warns: *"Please open YouTube first."*
- If the video toggles when switching focus, verify `CLICK_MODE = "safe_area"` in `config.py` (which clicks below the player rather than on the video).
- Run `python main.py --diagnose` to verify that both the `Gesture Classifier` and `YouTube Focus Manager` show `[ PASS ]`.

---

## Future Extension Points

SYRAX is architected with clear decoupling to support future modular capabilities:
- **Wake Word ("Hey SYRAX")**: Hooks defined in `config.FEATURE_WAKE_WORD_ENABLED` for local Porcupine / Snowboy / openWakeWord listeners.
- **Offline Speech Recognition**: Hooks for local Vosk or Whisper STT when no internet connection is available.
- **LLM Intent Engine**: `CommandParser._parse_with_llm()` hook ready to connect with Gemini or local LLM models for open-domain reasoning.
- **Context-Aware Multi-Turn Dialog**: Event bus structure allows saving historical dialog states for conversational follow-ups.
- **User Biometric Profiles**: Facial landmark and voiceprint authentication integration points.

---

## License

MIT License. Designed and engineered for high-reliability human-computer interaction on Windows.
