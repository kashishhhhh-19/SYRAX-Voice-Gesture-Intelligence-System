# SYRAX: Real-World Testing & Verification Checklist

**System**: SYRAX — Voice & Gesture Intelligence System for Windows 10/11
**Tagline**: *"Speak. Gesture. Control."*
**Date**: 2026-10-31
**Test Suite**: 88 Unit Tests Passing (100%)
**Hardware Self-Test**: 8/8 Subsystems Passed
**Automation Layer**: Chrome DevTools Protocol (CDP) via Playwright + Dedicated Profile (`%LOCALAPPDATA%\SYRAX\browser_profile`) with Win32 OS Fallback

---

## 1. Prerequisites & Environment Setup

Before performing real-world manual testing:
- [ ] Connect a laptop or desktop running Windows 10 or 11 with built-in Realtek microphone or external mic.
- [ ] Ensure webcam is unobstructed.
- [ ] Ensure default browser (Google Chrome, Microsoft Edge, or Brave) is installed.
- [ ] Run diagnostic self-test in terminal:
  ```powershell
  python main.py --diagnose
  ```
  Verify all 8 subsystems show `[ PASS ]`.
- [ ] Launch application:
  ```powershell
  python main.py
  ```
  Verify the dark cyberpunk dashboard appears with neon cyan accents, animated waveform, and Browser CDP indicator.
- [ ] Verify initial spoken greeting: *"Hello! I'm SYRAX. What would you like me to do?"*

---

## 2. Voice & Natural Language Understanding (Phase 1 & Upgrade Benchmarks)

Test the benchmark utterances across English, Hinglish, and Hindi (Devanagari):

| Test Case | Voice Command / Utterance | Expected System Action | Pass / Fail |
| :--- | :--- | :--- | :---: |
| **1.1** | *"SYRAX, play Barsaat by Banjare"* | Parses song='Barsaat', artist='Banjare'; launches top official video in managed browser profile; verifies playback via DOM; announces: *"Playing Barsaat by Banjare on YouTube."* | [ ] |
| **1.2** | *"Can you play Barsaat by Banjare?"* | Identifies conversational request; resolves artist='Banjare', song='Barsaat'; initiates YouTube playback. | [ ] |
| **1.3** | *"Let's watch a Python tutorial"* | Resolves query='Python tutorial'; opens YouTube search / top video in managed browser. | [ ] |
| **1.4** | *"Open Instagram and scroll reels"* | Opens `https://www.instagram.com/reels/` via BrowserManager CDP; checks login state; sets Active App to INSTAGRAM; announces: *"Opening Instagram Reels."* | [ ] |
| **1.5** | *"Rahul ko message bhejo ki how are you"* | Identifies Hinglish intent, extracts contact='Rahul', message='how are you'; drafts message into WhatsApp Web compose box; prompts readback confirmation. | [ ] |
| **1.6** | *"Find Rahul on WhatsApp and tell him I will call later"* | Extracts contact='Rahul', message='I will call later'; navigates to Rahul's chat; drafts message without pressing Enter. | [ ] |
| **1.7** | *"Send a WhatsApp message to Rahul"* | Detects missing message text; triggers slot-filling prompt: *"What message would you like to send to Rahul?"* | [ ] |
| **1.8** | *"haan bhejo"* (or *"yes"*, *"send it"*) | Approves pending draft; transmits message via Enter key; announces: *"Message sent to Rahul."* | [ ] |
| **1.9** | *"Pause this for a moment"* / *"Pause it"* | Context-aware pause; pauses YouTube or active reel; verifies `video.paused === true` via DOM. | [ ] |
| **1.10** | *"Play it again"* / *"Play again"* | Resumes active media; verifies playback via DOM. | [ ] |
| **1.11** | *"Close YouTube"* / *"यूट्यूब बंद करो"* | Closes only SYRAX-opened YouTube tab via CDP; SYRAX remains active. | [ ] |
| **1.12** | *"Close Instagram"* | Closes only SYRAX-opened Instagram tab via CDP; SYRAX remains active. | [ ] |
| **1.13** | *"Close WhatsApp"* | Closes only SYRAX-opened WhatsApp tab via CDP; SYRAX remains active. | [ ] |
| **1.14** | *"Close this website"* / *"Close tab"* | Closes current SYRAX-managed tab; SYRAX remains active. | [ ] |
| **1.15** | *"Close browser"* | Closes SYRAX-managed browser instance; SYRAX remains active. | [ ] |
| **1.16** | *"SYRAX, stop"* / *"रुको"* | **Instant Interrupt**: Halts active task / pauses playback; **never exits application**. | [ ] |
| **1.17** | *"Exit SYRAX"* / *"अलविदा"* | Clean application shutdown; speaks goodbye; terminates threads and closes GUI. | [ ] |

---

## 3. YouTube Voice Search & Ranking (Phase 2)

- [ ] **Exact Official Video Retrieval**:
  - Command: *"SYRAX, play Barsaat by Banjare"*
  - Result: The top official track is selected over 1-hour loops or amateur covers.
  - Browser automatically navigates to `https://www.youtube.com/watch?v=...`.
  - Spoken response: *"Playing Barsaat by Banjare on YouTube."*
- [ ] **Fallback Handling**:
  - Test offline or with unusual query: *"SYRAX, play xyzzyunknownsong12345"*
  - Result: SYRAX falls back gracefully to `https://www.youtube.com/results?search_query=...` without crashing.
- [ ] **Window Focus Enforcement**:
  - Switch focus to Notepad or another window while YouTube is playing.
  - Command: *"pause"* or *"next video"*
  - Result: FocusManager restores and foregrounds the YouTube window, applies safe-area click, and dispatches shortcut.

---

## 4. YouTube Hand Gesture Controls (Phase 3)

Toggle Gesture Mode ON by clicking **CAMERA ON** on dashboard or holding a closed Fist toward the webcam for ~1.0 second.

- [ ] **Fist Toggle Mode**:
  - Hold closed Fist in front of webcam for ~1.0s.
  - Mode transitions from IDLE to ACTIVE; dashboard pill turns Green; audio confirms: *"Gesture control active."*
  - Hold closed Fist again for ~1.0s -> transitions back to IDLE.
- [ ] **Play / Pause (Steady Open Palm)**:
  - While video is playing, present Open Palm facing camera and hold steady for ~0.5s.
  - Video pauses (or resumes).
- [ ] **Next Video (Swipe Right)**:
  - Sweep hand briskly from left to right.
  - Shortcut `Shift + N` skips to next video.
- [ ] **Previous Video (Swipe Left)**:
  - Sweep hand briskly from right to left.
  - Shortcut `Shift + P` (or Alt+Left) navigates to previous video.
- [ ] **Fast Forward 10s (Two-Finger Right)**:
  - Extend index and middle fingers (peace sign) and move toward the right.
  - Video skips forward 10 seconds.
- [ ] **Rewind 10s (Two-Finger Left)**:
  - Extend index and middle fingers and move toward the left.
  - Video rewinds 10 seconds.
- [ ] **Scroll Down (One-Finger Up)**:
  - Extend index finger pointing up.
  - Page scrolls smoothly down in continuous steps.
- [ ] **Scroll Up (One-Finger Down)**:
  - Extend index finger pointing down.
  - Page scrolls smoothly up in continuous steps.
- [ ] **Zoom In (Pinch Out)**:
  - Move thumb and index finger apart.
  - Webpage zooms in (Ctrl + Plus).
- [ ] **Zoom Out (Pinch In)**:
  - Bring thumb and index finger together.
  - Webpage zooms out (Ctrl + Minus).

---

## 5. Instagram Reels Voice & Gesture Browsing (Phase 4)

- [ ] **Open Reels**:
  - Command: *"SYRAX, open Instagram and scroll reels"*
  - Browser opens `https://www.instagram.com/reels/`.
  - Active App updates to `INSTAGRAM`.
- [ ] **Reel Navigation**:
  - Command: *"next reel"* -> advances to next reel via Down arrow.
  - Command: *"previous reel"* -> returns to previous reel via Up arrow.
  - Command: *"pause"* -> toggles reel video playback via Spacebar.
- [ ] **Reel Hand Gestures**:
  - In Instagram mode, One-Finger Up advances to next reel.
  - In Instagram mode, One-Finger Down returns to previous reel.
  - Steady Open Palm toggles reel pause/play.
- [ ] **Profile Isolation**:
  - Verify that Instagram gestures do not execute YouTube-specific keys (`k`, `l`, `j`, `Shift+N`).

---

## 6. WhatsApp Web Voice Messaging with Confirmation Gate (Phase 5)

> [!IMPORTANT]
> **Zero Credential & Explicit Confirmation Guarantee**
> SYRAX never asks for passwords or QR codes and **never** sends a WhatsApp message without explicit verbal confirmation or manual click of the green "Send" button.

- [ ] **Missing Contact Prompt**:
  - Command: *"Send a WhatsApp message saying hello"*
  - SYRAX asks: *"Who would you like to message on WhatsApp?"*
  - Response: *"Rahul"*
  - SYRAX drafts message to Rahul.
- [ ] **Missing Content Prompt**:
  - Command: *"Send a WhatsApp message to Rahul"*
  - SYRAX asks: *"What message would you like to send to Rahul?"*
  - Response: *"I will reach in 10 minutes"*
  - SYRAX drafts message into chat box.
- [ ] **Drafting Without Sending**:
  - Command: *"SYRAX, send Rahul a WhatsApp message saying how are you"*
  - Focuses WhatsApp Web search, searches contact "Rahul", enters chat, types "how are you" into compose box.
  - **VERIFY**: The message sits in the compose box. Enter is **NOT** pressed.
- [ ] **Spoken Readback & Confirmation Card**:
  - SYRAX reads back: *"I drafted a message to Rahul: 'how are you'. Should I send it?"*
  - The Yellow Confirmation Card appears on the dashboard with `[SEND (Yes)]` and `[CANCEL (No)]` buttons.
- [ ] **Explicit Approval to Send**:
  - Spoken: *"haan bhejo"* (or *"send it"*, *"yes"*, or click green SEND button).
  - SYRAX presses Enter, sends the message, confirms: *"Message sent to Rahul."*
  - Confirmation card dismisses.
- [ ] **Explicit Rejection / Cancellation**:
  - For a new drafted message, say: *"cancel"* (or *"mat bhejo"*, *"no"*, or click red CANCEL button).
  - SYRAX clears text from compose box (Ctrl+A, Backspace).
  - Spoken confirmation: *"Message cancelled."*
  - Confirmation card dismisses.
- [ ] **Privacy Verification**:
  - Check `logs/syrax.log`.
  - Verify message text is **NOT** logged into persistent log files.

---

## 7. Context-Aware Command Routing (Phase 6)

- [ ] **Context "Next"**:
  - With YouTube active in foreground, say: *"next"* -> skips to next video (`Shift+N`).
  - With Instagram active in foreground, say: *"next"* -> advances to next reel (`Down arrow`).
- [ ] **Context "Stop"**:
  - With YouTube playing, say: *"stop"* -> pauses video (`k`).
  - With Instagram playing, say: *"stop"* -> pauses reel (`Space`).
  - Neither command closes SYRAX.

---

## 8. Dashboard Telemetry & Controls (Phase 7)

- [ ] **Active Application Pill**:
  - Displays `YOUTUBE` when YouTube is in foreground.
  - Displays `INSTAGRAM` when Instagram is in foreground.
  - Displays `WHATSAPP` when WhatsApp is in foreground.
  - Displays `GENERAL` when desktop or other app is focused.
- [ ] **Intent & Entity Readout**:
  - Displays the last recognized command intent (e.g. `PLAY_MUSIC`, `SEND_MESSAGE`).
- [ ] **Universal Stop / Cancel Button**:
  - Click the prominent red `[STOP / CANCEL]` button on the dashboard at any time.
  - Instantly halts active background tasks, stops speech, and pauses playback.
- [ ] **Microphone Dropdown**:
  - Realtek built-in microphone is selected by default.
  - Selecting another input device from dropdown switches capture instantly without restarting application.

---

## 9. Troubleshooting & Recovery Matrix

| Issue | Root Cause | Solution |
| :--- | :--- | :--- |
| **"Microphone is unavailable"** | Device in exclusive use by another app or permissions restricted | Check Windows Microphone Privacy Settings (`Settings > Privacy > Microphone`). Run `python main.py --diagnose`. |
| **"Please open YouTube first"** | YouTube window is not open in the browser | Open YouTube in Chrome or Edge and start playing a video. |
| **"Please scan QR code to log in"** | WhatsApp Web session expired | Open `web.whatsapp.com` in your browser and link your mobile device. |
| **Spoken words not recognized** | High ambient background noise | Click **Calibrate Noise** button on dashboard while staying quiet for 1 second. |
| **Webcam preview black / sluggish** | Another app (Zoom, Teams) holds camera exclusive lock | Close other video applications and click **CAMERA OFF** then **CAMERA ON**. |
