"""
config.py - SYRAX Voice & Gesture Intelligence System Configuration
Centralized settings, thresholds, theme colors, and personality responses.
"""

from pathlib import Path

# ==============================================================================
# 1. CORE APPLICATION METADATA
# ==============================================================================
APP_NAME = "SYRAX"
TAGLINE = "Speak. Gesture. Control."
VERSION = "1.0.0"
AUTHOR = "Antigravity Engineering"
GREETING_TEXT = "Hello! I'm SYRAX. What would you like me to do?"

# Paths
BASE_DIR = Path(__file__).resolve().parent
LOG_DIR = BASE_DIR / "logs"
LOG_FILE = LOG_DIR / "syrax.log"

# ==============================================================================
# 2. VOICE & AUDIO CONFIGURATION
# ==============================================================================
# Audio capture settings
DEFAULT_SAMPLE_RATE = 16000
CHUNK_SIZE = 1024

# Energy threshold for silence detection (auto-adjusts during noise calibration)
ENERGY_THRESHOLD = 300
DYNAMIC_ENERGY_THRESHOLD = True
DYNAMIC_ENERGY_ADJUSTMENT_DAMPING = 0.15
DYNAMIC_ENERGY_RATIO = 1.5

# Timing thresholds (in seconds)
PAUSE_THRESHOLD = 0.8          # Silence duration to consider phrase finished
PHRASE_TIME_LIMIT = 6.0        # Max duration for a single utterance
LISTEN_TIMEOUT = 5.0           # Max time waiting for user to start speaking
AMBIENT_CALIBRATION_DURATION = 1.0  # Duration for ambient noise sampling
MAX_CONSECUTIVE_VOICE_FAILURES = 3   # Auto-recalibrates noise after repeated failures

# Preferred microphone name match (defaults to built-in Realtek mic if found)
PREFERRED_MIC_KEYWORD = "Realtek"

# Natural language command parser settings
FUZZY_MATCH_CUTOFF = 0.75

# ==============================================================================
# 3. TEXT-TO-SPEECH (TTS) CONFIGURATION
# ==============================================================================
TTS_ENGINE_PREFERENCE = ["sapi5", "pyttsx3"]
TTS_RATE = 175                 # Speaking speed (words per minute)
TTS_VOLUME = 1.0               # Output volume (0.0 to 1.0)
TTS_VOICE_INDEX = 0            # 0 for default SAPI voice (usually Microsoft David or Zira)

# ==============================================================================
# 4. GESTURE INTELLIGENCE CONFIGURATION
# ==============================================================================
CAMERA_INDEX = 0
CAMERA_WIDTH = 640
CAMERA_HEIGHT = 480
CAMERA_FPS = 30

# State Machine States
GESTURE_STATE_IDLE = "IDLE"
GESTURE_STATE_ACTIVE = "ACTIVE"
GESTURE_STATE_EXIT = "EXIT"

# Hold Durations & Steady Checks
FIST_HOLD_DURATION_SECONDS = 0.95      # Hold Fist ~1.0s to toggle mode ON/OFF
OPEN_PALM_STEADY_DURATION_SECONDS = 0.45 # Steady Open Palm held ~0.5s for Play/Pause
PALM_MAX_MOVEMENT_SPEED = 0.05         # Maximum movement threshold; faster is a swipe!

# Cooldowns and Debouncing (in seconds)
GESTURE_COOLDOWN_SECONDS = 0.8
SCROLL_COOLDOWN_SECONDS = 0.12
PINCH_COOLDOWN_SECONDS = 0.4
TWO_FINGER_COOLDOWN_SECONDS = 0.7
SWIPE_COOLDOWN_SECONDS = 0.8
FIST_TOGGLE_COOLDOWN_SECONDS = 1.5

# Landmark Smoothing & Detection Parameters
SMOOTHING_WINDOW_SIZE = 5              # Rolling average window size for landmarks
SWIPE_VELOCITY_THRESHOLD = 0.08        # Normalized horizontal displacement over window
TWO_FINGER_VELOCITY_THRESHOLD = 0.06   # Horizontal movement threshold for 2-finger forward/rewind
SWIPE_MIN_FRAMES = 3                   # Minimum consecutive direction frames for swipe
PINCH_THRESHOLD = 0.06                 # Normalized distance between thumb and index tip
PINCH_DISTANCE_DELTA_THRESHOLD = 0.015 # Distance change to classify pinch out vs pinch in
FINGER_EXTENDED_THRESHOLD = 0.04       # Y-delta to determine if finger is extended
SCROLL_STEP = 240                      # Mouse wheel scroll delta
SCROLL_REPEAT_INTERVAL = 0.14          # Repeat interval for continuous one-finger scroll
PINCH_REPEAT_INTERVAL = 0.35           # Repeat interval for continuous pinch zoom

# Spoken confirmations for gestures
GESTURE_VOICE_FEEDBACK_ENABLED = True  # Can be toggled live from UI
GESTURE_VOICE_ANNOUNCEMENT_THROTTLE_SECONDS = 2.0 # No repeated voice announcement within 2s

# ==============================================================================
# 5. YOUTUBE BROWSER FOCUS MANAGEMENT CONFIGURATION
# ==============================================================================
YOUTUBE_TITLE_KEYWORDS = ["youtube"]
BROWSER_PROCESS_NAMES = [
    "chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "opera.exe", "vivaldi.exe"
]
APP_WINDOW_TITLE_IGNORE = ["syrax"]
FOCUS_RETRY_COUNT = 3
FOCUS_DELAY_AFTER_FOREGROUND = 0.08     # Seconds to wait after SetForegroundWindow
FOCUS_DELAY_AFTER_CLICK = 0.05          # Seconds to wait after clicking tab
FOCUS_CACHE_SECONDS = 2.0               # Cache window for verified foreground
FOCUS_ATTEMPT_COOLDOWN_SECONDS = 0.4    # Minimum time between focus switch attempts

# Click safety mode:
# "safe_area": Clicks neutral spot below video player to focus without toggling playback.
# "player_center": Clicks video player center and accounts for playback effect.
CLICK_MODE = "safe_area"
CLICK_SAFE_AREA_X_RATIO = 0.50          # 50% across window width
CLICK_SAFE_AREA_Y_RATIO = 0.78          # Below typical video player
CLICK_PLAYER_CENTER_X_RATIO = 0.50
CLICK_PLAYER_CENTER_Y_RATIO = 0.45

YOUTUBE_NOT_FOUND_SPEECH_COOLDOWN = 5.0 # Seconds between repeated "Please open YouTube first" spoken warnings

# ==============================================================================
# 5. USER INTERFACE THEME (DARK / NEON CYAN & BLUE)
# ==============================================================================
# Backgrounds
COLOR_BG_DARK = "#080c14"       # Deep cosmos background
COLOR_BG_CARD = "#0f172a"       # Slate card container
COLOR_BG_PANEL = "#131e33"      # Elevated widget panel
COLOR_BG_INPUT = "#1a243b"      # Input field background

# Neon Accents
COLOR_CYAN_NEON = "#00f0ff"     # Primary brand cyan
COLOR_BLUE_NEON = "#0088ff"     # High-tech secondary blue
COLOR_GREEN_NEON = "#00ff88"    # Active / Success indicator
COLOR_RED_NEON = "#ff3366"      # Error / Alert indicator
COLOR_YELLOW_NEON = "#ffbb00"   # Warning / Calibrating indicator
COLOR_PURPLE_NEON = "#b026ff"   # Special action indicator

# Text & Borders
COLOR_TEXT_PRIMARY = "#f1f5f9"  # Crisp off-white
COLOR_TEXT_MUTED = "#94a3b8"    # Dimmed slate
COLOR_TEXT_DIM = "#64748b"      # Subtle dark slate
COLOR_BORDER = "#1e293b"        # Card border
COLOR_BORDER_GLOW = "#00f0ff"   # Focused glowing border

# Fonts
FONT_FAMILY = "Segoe UI"
FONT_MONO = "Consolas"

# ==============================================================================
# 6. SITES & SHORTCUTS
# ==============================================================================
QUICK_SITES = {
    "youtube": "https://www.youtube.com",
    "google": "https://www.google.com",
    "github": "https://www.github.com",
    "instagram": "https://www.instagram.com",
    "reddit": "https://www.reddit.com",
    "linkedin": "https://www.linkedin.com",
    "twitter": "https://www.x.com",
    "x": "https://www.x.com",
    "chatgpt": "https://chat.openai.com",
    "gmail": "https://mail.google.com",
    "spotify": "https://open.spotify.com",
}

# ==============================================================================
# 7. PERSONALITY & SPOKEN RESPONSES
# ==============================================================================
RESPONSES = {
    "startup": [
        "Hello! I'm SYRAX. What would you like me to do?",
    ],
    "greeting": [
        "Hello! I am SYRAX, ready for your commands.",
        "Greetings! Speak or gesture, and I will execute.",
        "Online and standing by. What can I do for you?",
    ],
    "youtube_open": [
        "YouTube is ready.",
        "Opening YouTube now.",
        "Launching YouTube in your browser.",
    ],
    "google_open": [
        "Google is ready.",
        "Opening Google now.",
    ],
    "site_open": [
        "Opening {site} now.",
        "Launching {site}.",
        "{site} is ready.",
    ],
    "searching": [
        "Searching for your request.",
        "Looking that up on Google.",
        "Searching the web for you.",
    ],
    "playing": [
        "Searching YouTube for {query}.",
        "Playing {query} on YouTube.",
        "Here are the YouTube results for {query}.",
    ],
    "playback_paused": [
        "Playback paused.",
        "Video paused.",
        "Holding playback.",
    ],
    "playback_resumed": [
        "Resuming playback.",
        "Playback resumed.",
        "Continuing playback.",
    ],
    "playback_next": [
        "Skipping to the next video.",
        "Next video playing.",
    ],
    "playback_previous": [
        "Returning to previous video.",
        "Previous video.",
    ],
    "playback_forward": [
        "Fast forwarding 10 seconds.",
        "Skipping ahead.",
    ],
    "playback_rewind": [
        "Rewinding 10 seconds.",
        "Jumping back.",
    ],
    "volume_up": [
        "Volume increased.",
        "Turning up the volume.",
    ],
    "volume_down": [
        "Volume decreased.",
        "Lowering volume.",
    ],
    "volume_mute": [
        "Audio muted.",
        "Sound muted.",
    ],
    "gesture_activated": [
        "Gesture control active. Ready for hand commands.",
        "Gesture tracking engaged.",
    ],
    "gesture_exited": [
        "Gesture control paused. Standing by.",
        "Gesture tracking idle.",
    ],
    "gesture_detected": [
        "Gesture recognized.",
    ],
    "unknown": [
        "Sorry, I didn't understand that.",
        "I did not catch that command.",
        "Unrecognized command. Please try again.",
    ],
    "mic_unavailable": [
        "Microphone is unavailable. Please run diagnostics to inspect audio devices.",
    ],
    "network_error": [
        "Speech recognition requires an internet connection. Please verify your network.",
    ],
    "shutdown": [
        "Goodbye! Shutting down SYRAX.",
        "SYRAX signing off. Have a great day!",
    ],
    "diagnostics_run": [
        "Running full system diagnostics now.",
    ],
    "youtube_not_found": [
        "Please open YouTube first.",
    ],
    "gesture_video_next": [
        "Next video.",
    ],
    "gesture_video_prev": [
        "Previous video.",
    ],
    "gesture_video_forward": [
        "Forwarding.",
    ],
    "gesture_video_rewind": [
        "Rewinding.",
    ],
    "gesture_zoom_in": [
        "Zooming in.",
    ],
    "gesture_zoom_out": [
        "Zooming out.",
    ],
}

# ==============================================================================
# 8. FUTURE EXTENSION POINTS (FLAGS & PLACEMENTS)
# ==============================================================================
# These define hooks for forthcoming modular capabilities
FEATURE_WAKE_WORD_ENABLED = False       # "Hey SYRAX" local wake-word listener
FEATURE_OFFLINE_STT_ENABLED = False     # Local offline Vosk / Whisper STT
FEATURE_LLM_INTENT_ENABLED = False      # Neural / LLM-based intent disambiguation
FEATURE_USER_PROFILES_ENABLED = False   # Multi-user biometric voice / gesture profiles
FEATURE_CONTEXTUAL_CONVO_ENABLED = False # Multi-turn dialog history context
