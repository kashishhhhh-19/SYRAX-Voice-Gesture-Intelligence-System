# SYRAX — Architecture & Technical Reference
**Voice & Gesture Intelligence System  ·  "Speak. Gesture. Control."**

---

## 1. High-Level Architectural Overview

SYRAX is an autonomous, multi-modal desktop intelligence system for Windows 10/11 designed to give users hands-free and voice-driven control over laptop media, social feeds, and messaging applications.

```
                           +-------------------------------------+
                           |            USER INPUTS              |
                           |  Mic (Voice)  |  Webcam (Gestures)  |
                           +------------------+------------------+
                                              |
                   +--------------------------+--------------------------+
                   |                                                     |
                   v                                                     v
        +----------------------+                              +----------------------+
        |     VoiceEngine      |                              |    GestureEngine     |
        | SpeechRecognition    |                              | OpenCV Hand Tracker  |
        | Built-in Realtek Mic |                              | Gesture Classifier   |
        +----------+-----------+                              +----------+-----------+
                   |                                                     |
                   v                                                     v
        +----------------------+                              +----------------------+
        |   CommandParser &    |                              |   GestureProfiles    |
        |   IntentClassifier   |                              | (YouTube / Instagram |
        |  (En, Hi, Hinglish)  |                              |   / Presentation)    |
        +----------+-----------+                              +----------+-----------+
                   |                                                     |
                   +--------------------------+--------------------------+
                                              |
                                              v
                               +-----------------------------+
                               |     ActionDispatcher &      |
                               |    ApplicationController    |
                               +--------------+--------------+
                                              |
                     +------------------------+------------------------+
                     |                                                 |
                     v                                                 v
        +---------------------------+                    +---------------------------+
        |   PRIMARY VERIFIABLE      |                    |       FALLBACK TIER       |
        |      CDP LAYER            |                    |      (OS AUTOMATION)      |
        |      BrowserManager       |                    |       FocusManager        |
        |  Chrome DevTools Protocol |                    |    Windows Win32 API      |
        | Playwright connect_over_cdp|                   |    PyAutoGUI Shortcuts    |
        +-------------+-------------+                    +-------------+-------------+
                      |                                                |
                      +-----------------------+------------------------+
                                              |
                                              v
                              +-------------------------------+
                              |    TARGET APPLICATIONS        |
                              |  YouTube | Instagram | WhatsApp|
                              +-------------------------------+
```

---

## 2. BrowserManager CDP Architecture

Prior versions relied on blind keystrokes (`k`, `space`, `down` arrow) dispatched via `pyautogui`. If a search box was active, if the window lost focus, or if video elements had not yet received focus, shortcuts failed silently with zero feedback.

SYRAX now implements a **Two-Tier Architecture**:

### Tier 1 (Primary): Chrome DevTools Protocol (CDP) via Playwright
- **Connection**: Playwright connects to the browser using `chromium.connect_over_cdp("http://127.0.0.1:9222")`.
- **Dedicated Persistent Profile**:
  `%LOCALAPPDATA%\SYRAX\browser_profile`
  - Ensures YouTube, Instagram, and WhatsApp Web user sessions and login cookies persist across restarts.
  - SYRAX never requests, accesses, or stores passwords, tokens, or credentials.
- **Verifiable DOM/JS Actions**:
  - **YouTube**: Direct execution of `video.pause()`, `video.play()`, and verification of `video.paused === true` / `false` and `video.currentTime`.
  - **Instagram Reels**: Direct DOM-triggered viewport scroll, button clicks, and video play/pause verification.
  - **WhatsApp Web**: Contact search, result extraction, compose box drafting, and verification that compose box is cleared upon send.

### Tier 2 (Fallback): Windows OS FocusManager
- When CDP is not available or if the browser was launched independently, SYRAX falls back to `FocusManager`:
  - Uses Windows Win32 API (`GetForegroundWindow`, `SetForegroundWindow`, `ShowWindow`) to guarantee target window focus.
  - Dispatches targeted keyboard shortcuts (`k`, `Shift+N`, `Shift+P`, `Ctrl+Alt+/`).

---

## 3. Strict Tab Isolation & Safety

SYRAX enforces an uncompromising tab tracking policy:
- **`_syrax_page_ids`**: Whenever SYRAX opens a new tab via `BrowserManager.open_tab()`, its unique internal ID is registered in `self._syrax_page_ids`.
- **Targeted Closing**: `close_tab(app_key)` strictly verifies that the tab to be closed belongs to `self._syrax_page_ids`.
- **Personal Tabs Protected**: Unrelated user tabs (e.g. Gmail, work documents, personal browsing) can never be closed by SYRAX.

---

## 4. Distinct Close vs. Exit Semantics

SYRAX strictly differentiates between closing a web tab and terminating the application:

| User Utterance | Intent | Action Executed | Application State |
| :--- | :--- | :--- | :--- |
| `"Close YouTube"` / `"यूट्यूब बंद करो"` | `CLOSE_YOUTUBE` | Closes SYRAX-opened YouTube tab | SYRAX stays active |
| `"Close Instagram"` / `"इंस्टाग्राम बंद करो"` | `CLOSE_INSTAGRAM` | Closes SYRAX-opened Instagram tab | SYRAX stays active |
| `"Close WhatsApp"` / `"व्हाट्सएप बंद करो"` | `CLOSE_WHATSAPP` | Closes SYRAX-opened WhatsApp tab | SYRAX stays active |
| `"Close this website"` / `"Close tab"` | `CLOSE_TAB` | Closes current SYRAX-managed tab | SYRAX stays active |
| `"Close browser"` | `CLOSE_BROWSER` | Closes SYRAX-managed browser instance | SYRAX stays active |
| `"Stop"` / `"रुको"` / `"Pause"` | `STOP` / `MEDIA_CONTROL` | Halts current task / pauses video | SYRAX stays active |
| `"Exit SYRAX"` / `"अलविदा"` | `EXIT` | Shuts down SYRAX background threads & GUI | SYRAX shuts down |

---

## 5. WhatsApp Web Confirmation Gate & Privacy

Sending WhatsApp messages via voice presents severe real-world risk if misheard. SYRAX implements an unbreakable confirmation gate:

1. **Contact & Message Extraction**: Resolves contact name and message text via `EntityExtractor`.
2. **Drafting Without Sending**: Navigates to contact chat and types text into compose box. **Enter is NEVER pressed.**
3. **Pending Confirmation State**: Recorded in `ConversationState.set_pending_confirmation()`.
4. **Readback & UI Card**:
   - Voice readback: *"I drafted a message to [Contact]: '[Message]'. Should I send it?"*
   - GUI card surfaces with `[SEND]` and `[CANCEL]` neon buttons.
5. **Execution Barrier**:
   - Only an explicit verbal affirmation (`"yes"`, `"send it"`, `"haan bhejo"`) or physical button click triggers message dispatch.
   - Rejection (`"no"`, `"cancel"`, `"mat bhejo"`) immediately clears text from the compose box.
6. **Privacy Guarantee**: Message content is strictly ephemeral and is never written to persistent log files on disk.

---

## 6. Multilingual NLU & Phonetic Tolerance

SYRAX supports natural conversation in English, Hindi (Devanagari script), and romanized Hinglish:
- **Heuristic Language Detection**: Identifies Devanagari Unicode (`\u0900-\u097F`), Hinglish vocabulary markers (`ko`, `karo`, `bhejo`, `chalao`, etc.), or standard English.
- **Contextual Pronouns**: Resolves follow-up commands (*"Pause it"*, *"Play again"*, *"Tell him I'll call later"*) using `ConversationState.last_contact` and `last_video_query`.
- **Typo & Accent Tolerance**: Multi-stage classification with regex anchors, phonetic aliases, and `difflib` sequence matching.
