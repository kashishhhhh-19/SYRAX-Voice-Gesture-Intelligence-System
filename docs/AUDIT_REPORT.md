# SYRAX Master Upgrade: Architecture Audit & Implementation Plan

**Date**: 2026-10-31
**Project**: SYRAX — Voice & Gesture Intelligence System ("Speak. Gesture. Control.")
**Author**: Senior Python Systems Engineer

---

## 1. Executive Summary

This audit assesses the current state of SYRAX following rigorous inspection of all codebase modules, execution of the existing 29 unit tests (100% passing), and hardware self-test diagnostic runs.

SYRAX currently possesses a solid architectural foundation:
- **Asynchronous Threading & Queue Infrastructure**: Dedicated worker threads for Voice capture (`VoiceEngine`), TTS speech synthesis (`TTSEngine`), and Gesture vision tracking (`GestureEngine`), communicating via a centralized, decoupled `EventBus` and marshaled onto the main Tkinter thread through `_ui_queue`.
- **Hardware Fallbacks**: Seamless fallback from PyAudio to `sounddevice`, adaptive OpenCV skin tracker fallback when MediaPipe is unavailable, and native Windows SAPI COM-based TTS.
- **Robust Windows Focus Manager**: `actions/focus_manager.py` with mockable `WindowAdapter` and Windows API implementations for window enumeration, foregrounding with Alt-key bypass, and safe-area clicking.

However, several critical architectural bottlenecks must be addressed to fulfill the mission requirements:
1. **Command Parser Brittleness**: Commands currently rely on exact regex patterns and a static difflib fuzzy dictionary. It cannot parse natural sentences ("SYRAX, play Barsaat by Banjare"), fails on Hinglish/Hindi phrasing ("Rahul ko message bhejo"), and cannot extract multi-part entities (song title vs. artist).
2. **Interrupt & "Stop" Inadequacy**: When SYRAX is speaking, the microphone listener thread sleeps (`if self._tts_engine.is_speaking(): time.sleep(0.1)`), making it impossible for a user to interrupt SYRAX with "Stop". Furthermore, actions execute synchronously inside `_on_voice_recognized`, blocking subsequent command ingestion.
3. **Application Siloing**: Window focus management is hardcoded for YouTube only. Instagram and WhatsApp require application-aware focus, dedicated gesture profiles, and conversational message confirmation flows.

---

## 2. Baseline Architecture Map

```
                                  +---------------------------------------+
                                  |            SYRAX Dashboard            |
                                  |         (Main Thread: Tkinter)        |
                                  +-------------------+-------------------+
                                                      ^
                                                      | _ui_queue.put() via EventBus
                                                      v
                                  +---------------------------------------+
                                  |           EventBus (Events)           |
                                  |      (Thread-Safe Pub/Sub Hub)        |
                                  +---+---------------+---------------+---+
                                      ^               ^               ^
                                      |               |               |
                   +------------------+               |               +------------------+
                   |                                  |                                  |
         +---------+---------+              +---------+---------+              +---------+---------+
         |    VoiceEngine    |              |  AssistantEngine  |              |   GestureEngine   |
         | (Background Daemon|              |  & ActionDispatcher|             | (Background Daemon|
         |  SoundDevice/PyAu)|              | (Command Dispatch)|              | OpenCV/MediaPipe) |
         +---------+---------+              +---------+---------+              +---------+---------+
                   |                                  |                                  |
                   |                                  v                                  |
                   |                        +---------+---------+                        |
                   |                        | FocusManager &    |                        |
                   |                        | Automation Drivers|                        |
                   +----------------------->| (PyAutoGUI, Browser)                      |
                                            +---------+---------+                        |
                                                      ^                                  |
                                                      |                                  |
                                            +---------+---------+                        |
                                            |     TTSEngine     |<-----------------------+
                                            | (Background Daemon|
                                            | Windows SAPI COM) |
                                            +-------------------+
```

### Thread & Queue Topology
| Thread Name | Function | Input / Output Queue | Current Weak Point |
| :--- | :--- | :--- | :--- |
| **MainThread** | Tkinter GUI event loop (`root.mainloop()`) | `_ui_queue` (25ms poll via `after()`) | Healthy. UI stays responsive. |
| **SYRAX-Voice-Worker** | Continuous microphone capture & Google STT | Audio stream -> `Events.VOICE_RECOGNIZED` | **Critical Weakness**: Sleeps while TTS speaks. Cannot hear "stop". |
| **SYRAX-TTS-Worker** | Windows SAPI / pyttsx3 speech synthesizer | `_speech_queue` | SAPI `Speak()` call is synchronous and non-interruptible. |
| **SYRAX-Gesture-Worker**| 30 FPS webcam grab & landmark classifier | Video frame -> `Events.GESTURE_FRAME` | Lacks application-specific profiles (YouTube vs Instagram). |
| **SYRAX-NetCheck** | Periodic Google reachability ping (10s) | Emits `NET_STATUS` | Healthy. |

---

## 3. Current Weak Points & Failure Modes

1. **Voice Parsing Rigidity**:
   - `CommandParser.parse()` checks regexes like `r"^play (.+)$"`. If the user says "Can you please play Barsaat by Banjare" or "SYRAX play Barsaat", it either misidentifies the query as `"barsaat by banjare"` without parsing artist/title, or falls through to `UNKNOWN`.
   - No support for multilingual or Hinglish utterances (e.g. *"gaana chalao"*, *"ruko"*, *"bhai message bhejo"*).
2. **Global "Stop" & Interrupt Failure**:
   - If an action takes time (e.g., waiting for browser navigation or scrolling), there is no cancellation token (`threading.Event`).
   - "Stop" does not halt running loops or audio output immediately.
   - Disambiguation between "Stop" (halt activity) and "Exit SYRAX" (close application) is missing.
3. **Focus Manager Limitations**:
   - `FocusManager` only searches for `"youtube"` in window titles. It cannot detect or focus Instagram or WhatsApp Web tabs.
4. **YouTube Voice Search & Playback**:
   - Currently, `play_youtube` simply opens `https://www.youtube.com/results?search_query=...`. It never actually inspects results, ranks them, or starts playback automatically. It leaves the user stranded on the search results page.
5. **No WhatsApp or Instagram Integrations**:
   - WhatsApp and Instagram action handlers, gesture profiles, and safety confirmation loops do not yet exist.

---

## 4. Browser Automation Strategy Decision

**Requirement**: Reuse the user's existing logged-in browser session without demanding credentials, tokens, or security bypasses.

### Evaluation of Options:
- **Option A (CDP Attach via Remote Debugging Port)**: Powerful DOM access, but requires Chrome/Edge to be started with `--remote-debugging-port=9222`. Standard Windows users double-click Chrome/Edge without CLI flags, meaning standard instances reject CDP connections.
- **Option B (Dedicated Persistent SYRAX Browser Profile)**: Launches an isolated profile folder. User must log into Google, WhatsApp, and Instagram a second time inside this custom profile.
- **Option C (OS-Level Window Detection, Focus & Deep URLs with Browser Shortcuts)**:
  - Detects existing browser windows (Chrome, Edge, Brave, Firefox, Opera) using `win32gui` and window title matching.
  - Brings the exact tab/window to the foreground using Windows API workarounds.
  - Launches deep direct URLs (`https://www.youtube.com/results?search_query=...`, `https://www.instagram.com/reels/`, `https://web.whatsapp.com/send?phone=...` or standard WhatsApp Web chat search) using the system default browser, thereby inheriting the user's existing active cookies and logins.
  - Uses targeted keyboard shortcuts (`Shift+N`, `k`, `j`, `l`, `/` or `Ctrl+Alt+/` in WhatsApp, `Down Arrow` in Reels) to interact cleanly with zero credential handling.

### Selected Strategy: **Hybrid Adaptive Strategy (Option C Primary + Optional CDP Enhancer)**
1. **Primary Foundation**: OS-Level Focus Management + Deep URL Routing + Native Application Shortcuts. This guarantees 100% compatibility with the user's existing default browser and active logins out of the box, with zero friction and zero security bypasses.
2. **DOM Extraction Helper**: For YouTube title parsing and WhatsApp contact resolution, we provide a clean, non-intrusive scraping/query helper that can query open tabs via lightweight automation or fallback to intelligent keyboard navigation and direct web endpoints.
3. **Isolated Selectors**: All site selectors and shortcuts are encapsulated in `config.py` and dedicated action modules so UI changes can be patched in one place.

---

## 5. File-by-File Upgrade Plan (Mapped to Phases)

### Phase 1: Natural-Language Understanding & Global Interrupts
- `core/command_parser.py`: Upgrade to return structured intent + entities + language classification; integrate fuzzy matching and alias normalization.
- `core/intent_classifier.py` *(New)*: Multi-intent classifier supporting natural phrasing, Hinglish/Hindi variations, and intent confidence scoring.
- `core/entity_extractor.py` *(New)*: Extracts song titles, artists, app names, contact names, message text, and numeric parameters.
- `core/conversation_state.py` *(New)*: Manages multi-turn conversation context (pending slots, active app, confirmation state).
- `core/interrupt_manager.py` *(New)*: High-priority interrupt handler with cancellation tokens (`threading.Event`) and immediate SAPI purge.
- `voice/tts_engine.py`: Add `stop_speech()` / `purge()` method using Windows SAPI `SpVoice.Speak("", SVSFPurgeBeforeSpeak)` or asynchronous speech flags.
- `voice/voice_engine.py`: Update listen loop so interrupts ("stop", "ruko", "cancel") are detected even during prompt playback, without self-triggering loops.

### Phase 2: YouTube Voice Search, Ranking & Playback
- `actions/youtube_actions.py` *(New)*: Workflow for title/artist extraction, searching, result scoring/ranking (preferring official/topic channels), navigating to top video, and verifying playback.
- `actions/focus_manager.py`: Generalize to support YouTube, Instagram, WhatsApp, and general browsers.

### Phase 3: YouTube Gesture Control & Gesture Profiles
- `gesture/gesture_profiles.py` *(New)*: Per-application gesture profiles (YouTube profile, Instagram profile, General profile).
- `gesture/gesture_engine.py` & `gesture/gesture_actions.py`: Hook into active gesture profile.

### Phase 4: Instagram Voice & Gesture Control
- `actions/instagram_actions.py` *(New)*: Open Instagram, open Reels, next/previous reel navigation, pause/resume, and login/challenge detection.
- `gesture/gesture_profiles.py`: Add Instagram-specific gestures (Swipe Up -> Next Reel, Swipe Down -> Previous Reel, Open Palm -> Play/Pause).

### Phase 5: WhatsApp Web Voice Messaging
- `actions/whatsapp_actions.py` *(New)*: Search contacts, select recipient, capture dictation, compose without sending, read-back confirmation prompt, and explicit spoken send confirmation ("yes" / "send it" / "haan bhejo"). Strict cancellation at all stages.
- Privacy protection: Message content only in transient confirmation card; never in persistent logs.

### Phase 6: Application-Aware Command Routing
- `core/application_controller.py` *(New)*: Detects active foreground application, disambiguates context-sensitive commands ("next", "stop", "reply"), and routes to the correct handler.
- `core/assistant_engine.py`: Integrate application controller into processing pipeline.

### Phase 7: Conversational Assistant & Dashboard Enhancements
- `gui/dashboard.py` & `gui/widgets.py`: Add Active Application indicator, Current Intent & Entity readout, YouTube/Instagram/WhatsApp application cards, and Pending Message Confirmation Card (with Send / Cancel buttons).
- Varied conversational response templates in `config.py`.

### Phase 8: Testing & Verification
- Comprehensive test suite: `tests/test_intent_classifier.py`, `tests/test_entity_extractor.py`, `tests/test_interrupt_manager.py`, `tests/test_application_controller.py`, `tests/test_youtube_actions.py`, `tests/test_whatsapp_actions.py`, `tests/test_instagram_actions.py`, `tests/test_gesture_profiles.py`.
- Documentation: `docs/REAL_WORLD_TEST_CHECKLIST.md`.

---

## 6. Implementation & Verification Status Matrix

| Module / Feature | Component / File | Verification Method | Status |
| :--- | :--- | :--- | :--- |
| **Natural Language & Phrasing** | `core/intent_classifier.py`, `core/entity_extractor.py` | 24 Unit tests covering English, Hindi, Hinglish, entity slots | **Verified (Unit tested)** |
| **Multi-Turn & Confirmation State**| `core/conversation_state.py` | Unit tests for slot-filling, confirmation gates, auto-expiry | **Verified (Unit tested)** |
| **Global High-Priority Interrupt** | `core/interrupt_manager.py`, `voice/tts_engine.py` | Unit tests with mock TTS purge, `threading.Event` tokens | **Verified (Unit tested)** |
| **Command Parser & 11 Utterances** | `core/command_parser.py`, `tests/test_command_parser.py` | 13 Unit tests validating all Table 2.1 benchmark sentences | **Verified (Unit tested)** |
| **YouTube Voice Search & Ranking** | `actions/youtube_actions.py` | 5 Unit tests with candidate scoring, loops penalty, fallback | **Verified (Unit tested)** |
| **YouTube Focus Manager** | `actions/focus_manager.py` | 7 Unit tests with mock OS WindowAdapter, caching & clicking | **Verified (Unit tested & Live Diagnosed)** |
| **YouTube Gesture Control** | `gesture/gesture_classifier.py`, `gesture/gesture_profiles.py`| 13 Unit tests for Fist hold, Palm steady, Swipes, Pinch | **Verified (Unit tested)** |
| **Instagram Reels Automation** | `actions/instagram_actions.py`, `tests/test_instagram_actions.py`| 5 Unit tests for window detection, down/up key dispatch | **Verified (Unit tested)** |
| **Gesture Profiles & Isolation** | `gesture/gesture_profiles.py`, `gesture/gesture_actions.py` | 5 Unit tests verifying YouTube vs Instagram isolation | **Verified (Unit tested)** |
| **WhatsApp Voice Messaging** | `actions/whatsapp_actions.py`, `tests/test_whatsapp_actions.py` | 6 Unit tests for slot prompts, drafting, confirmation gate | **Verified (Unit tested)** |
| **Contextual Application Routing** | `core/application_controller.py` | 5 Unit tests verifying foreground detection and command routing | **Verified (Unit tested)** |
| **Futuristic Dashboard** | `gui/dashboard.py` | Real Tkinter initialization test, event subscription, status pills | **Verified (GUI launch tested)** |
| **Subsystem Self-Test** | `main.py --diagnose` | Live hardware test across Mic, STT, SAPI, Camera, PyAutoGUI | **Verified (Live hardware passed)** |
