"""
core/action_dispatcher.py - Central Action Execution and Response Dispatcher
Dispatches structured Commands to Browser, Media, Presentation, and System handlers.
Selects personality-driven spoken responses and updates system state through the EventBus.
"""

import random
from dataclasses import dataclass
from typing import Optional

import config
from actions.browser_actions import BrowserActions
from actions.media_actions import MediaActions
from actions.presentation_actions import PresentationActions
from core.command_parser import Command, CommandIntent
from core.event_bus import Events, get_event_bus
from core.logger import get_logger
from voice.tts_engine import TTSEngine

logger = get_logger("ActionDispatcher")


@dataclass
class ActionResult:
    """Outcome of an executed command."""
    success: bool
    response_text: str
    spoken_text: str
    intent: CommandIntent
    raw_command: str


class ActionDispatcher:
    """
    Executes parsed user commands and coordinates spoken audio responses.
    """

    def __init__(self, tts_engine: Optional[TTSEngine] = None) -> None:
        self._event_bus = get_event_bus()
        self._tts_engine = tts_engine

    def dispatch(self, command: Command) -> ActionResult:
        """
        Execute the specified command and trigger spoken audio feedback.
        """
        logger.info(f"Dispatching intent: {command.intent} | raw: '{command.raw_text}'")

        handler_map = {
            CommandIntent.GREETING: self._handle_greeting,
            CommandIntent.OPEN_SITE: self._handle_open_site,
            CommandIntent.SEARCH: self._handle_search,
            CommandIntent.PLAY: self._handle_play,
            CommandIntent.MEDIA_CONTROL: self._handle_media_control,
            CommandIntent.VOLUME_CONTROL: self._handle_volume_control,
            CommandIntent.PRESENTATION_CONTROL: self._handle_presentation_control,
            CommandIntent.GESTURE_MODE: self._handle_gesture_mode,
            CommandIntent.STOP: self._handle_stop,
            CommandIntent.STOP_MUSIC: self._handle_stop_music,
            CommandIntent.STOP_VIDEO: self._handle_stop_video,
            CommandIntent.STOP_SCROLLING: self._handle_stop_scrolling,
            CommandIntent.CANCEL_MESSAGE: self._handle_cancel_message,
            CommandIntent.CANCEL_OPERATION: self._handle_stop,
            CommandIntent.CLOSE_YOUTUBE: self._handle_close_youtube,
            CommandIntent.CLOSE_INSTAGRAM: self._handle_close_instagram,
            CommandIntent.CLOSE_WHATSAPP: self._handle_close_whatsapp,
            CommandIntent.CLOSE_TAB: self._handle_close_tab,
            CommandIntent.CLOSE_BROWSER: self._handle_close_browser,
            CommandIntent.SCROLL_FEED: self._handle_scroll_feed,
            CommandIntent.SEND_MESSAGE: self._handle_send_message,
            CommandIntent.CONFIRMATION: self._handle_confirmation,
            CommandIntent.DIAGNOSTICS: self._handle_diagnostics,
            CommandIntent.EXIT: self._handle_exit,
            CommandIntent.UNKNOWN: self._handle_unknown,
        }

        handler = handler_map.get(command.intent, self._handle_unknown)
        result = handler(command)

        # Notify system of executed action
        self._event_bus.emit(
            Events.ACTION_EXECUTED,
            success=result.success,
            response=result.response_text,
            spoken=result.spoken_text,
            command=command.raw_text,
            intent=command.intent.value,
            source=command.source
        )

        # Spoken audio confirmation via TTS
        if result.spoken_text and self._tts_engine:
            self._tts_engine.speak(result.spoken_text)

        return result

    def _pick_response(self, category: str, **kwargs: str) -> str:
        """Pick a response variation from config.RESPONSES and format variables."""
        templates = config.RESPONSES.get(category, ["Action completed."])
        template = random.choice(templates)
        try:
            return template.format(**kwargs)
        except Exception:
            return template

    def _handle_greeting(self, command: Command) -> ActionResult:
        spoken = self._pick_response("greeting")
        return ActionResult(
            success=True,
            response_text=spoken,
            spoken_text=spoken,
            intent=command.intent,
            raw_command=command.raw_text
        )

    def _handle_open_site(self, command: Command) -> ActionResult:
        target = (command.target or "browser").lower()
        if "instagram" in target and (command.action == "open_reels" or command.parameters.get("mode") == "reels"):
            from actions.instagram_actions import get_instagram_actions
            success, msg, spoken = get_instagram_actions().open_instagram(reels=True)
            return ActionResult(
                success=success,
                response_text=msg,
                spoken_text=spoken,
                intent=command.intent,
                raw_command=command.raw_text
            )

        success, msg = BrowserActions.open_site(target)
        if target == "youtube":
            spoken = self._pick_response("youtube_open")
        elif target == "google":
            spoken = self._pick_response("google_open")
        else:
            spoken = self._pick_response("site_open", site=target.capitalize())

        return ActionResult(
            success=success,
            response_text=msg,
            spoken_text=spoken,
            intent=command.intent,
            raw_command=command.raw_text
        )

    def _handle_scroll_feed(self, command: Command) -> ActionResult:
        from actions.instagram_actions import get_instagram_actions
        ig = get_instagram_actions()
        action = command.action or "scroll_down"
        if action in ("scroll_up", "previous_reel", "up"):
            success, msg = ig.previous_reel()
            spoken = "Previous reel."
        else:
            success, msg = ig.next_reel()
            spoken = "Next reel."

        return ActionResult(
            success=success,
            response_text=f"Instagram: {msg}",
            spoken_text=spoken,
            intent=command.intent,
            raw_command=command.raw_text
        )

    def _handle_search(self, command: Command) -> ActionResult:
        query = command.query or ""
        success, msg = BrowserActions.search_google(query)
        spoken = self._pick_response("searching")
        return ActionResult(
            success=success,
            response_text=f"Searched Google for: '{query}'",
            spoken_text=spoken,
            intent=command.intent,
            raw_command=command.raw_text
        )

    def _handle_play(self, command: Command) -> ActionResult:
        from actions.youtube_actions import get_youtube_actions
        yt = get_youtube_actions()
        query = command.query or ""
        song_title = command.parameters.get("song_title")
        artist = command.parameters.get("artist")
        success, msg, spoken = yt.play_best_match(
            query=query,
            song_title=song_title,
            artist=artist
        )
        return ActionResult(
            success=success,
            response_text=f"YouTube: {msg}",
            spoken_text=spoken,
            intent=command.intent,
            raw_command=command.raw_text
        )

    def _handle_media_control(self, command: Command) -> ActionResult:
        action = command.action or "toggle"
        from core.application_controller import get_application_controller, AppContext
        app_ctrl = get_application_controller()
        ctx = app_ctrl.detect_foreground_app()
        if ctx in (AppContext.YOUTUBE, AppContext.INSTAGRAM):
            success, msg, spoken = app_ctrl.route_context_action(action)
            return ActionResult(
                success=success,
                response_text=msg,
                spoken_text=spoken or "Action executed.",
                intent=command.intent,
                raw_command=command.raw_text
            )

        if action == "pause":
            success, msg = MediaActions.pause_playback()
            spoken = self._pick_response("playback_paused")
        elif action == "resume":
            success, msg = MediaActions.resume_playback()
            spoken = self._pick_response("playback_resumed")
        elif action == "next":
            success, msg = MediaActions.next_track()
            spoken = self._pick_response("playback_next")
        elif action == "previous":
            success, msg = MediaActions.previous_track()
            spoken = self._pick_response("playback_previous")
        elif action == "forward":
            success, msg = MediaActions.fast_forward(10)
            spoken = self._pick_response("playback_forward")
        elif action == "rewind":
            success, msg = MediaActions.rewind(10)
            spoken = self._pick_response("playback_rewind")
        else:
            success, msg = MediaActions.toggle_play_pause()
            spoken = "Toggled playback."

        return ActionResult(
            success=success,
            response_text=msg,
            spoken_text=spoken,
            intent=command.intent,
            raw_command=command.raw_text
        )

    def _handle_volume_control(self, command: Command) -> ActionResult:
        action = command.action or "volume_up"
        amount = command.parameters.get("amount")
        steps = max(1, int(amount) // 2) if amount else 3
        if action == "volume_up":
            success, msg = MediaActions.volume_up(steps=steps)
            spoken = self._pick_response("volume_up")
        elif action == "volume_down":
            success, msg = MediaActions.volume_down(steps=steps)
            spoken = self._pick_response("volume_down")
        elif action == "mute":
            success, msg = MediaActions.toggle_mute()
            spoken = self._pick_response("volume_mute")
        else:
            success, msg = False, "Unknown volume command."
            spoken = ""

        return ActionResult(
            success=success,
            response_text=msg,
            spoken_text=spoken,
            intent=command.intent,
            raw_command=command.raw_text
        )

    def _handle_presentation_control(self, command: Command) -> ActionResult:
        action = command.action or "next"
        if action == "next":
            success, msg = PresentationActions.next_slide()
        elif action == "previous":
            success, msg = PresentationActions.previous_slide()
        elif action == "zoom_in":
            success, msg = PresentationActions.zoom_in()
        elif action == "zoom_out":
            success, msg = PresentationActions.zoom_out()
        else:
            success, msg = PresentationActions.next_slide()

        return ActionResult(
            success=success,
            response_text=msg,
            spoken_text=msg,
            intent=command.intent,
            raw_command=command.raw_text
        )

    def _handle_gesture_mode(self, command: Command) -> ActionResult:
        action = command.action or "start"
        if action == "start":
            self._event_bus.emit(
                Events.GESTURE_STATUS_CHANGED,
                status=config.GESTURE_STATE_ACTIVE,
                message="Gesture Control ENGAGED via voice command."
            )
            self._event_bus.emit(
                Events.GESTURE_MODE_TOGGLED,
                state=config.GESTURE_STATE_ACTIVE,
                message="Gesture Mode: ACTIVE"
            )
            spoken = config.RESPONSES["gesture_activated"][0]
            resp_text = "Gesture Control Mode activated."
        else:
            self._event_bus.emit(
                Events.GESTURE_STATUS_CHANGED,
                status=config.GESTURE_STATE_IDLE,
                message="Gesture Control PAUSED via voice command."
            )
            self._event_bus.emit(
                Events.GESTURE_MODE_TOGGLED,
                state=config.GESTURE_STATE_IDLE,
                message="Gesture Mode: IDLE"
            )
            spoken = config.RESPONSES["gesture_exited"][0]
            resp_text = "Gesture Control Mode paused."

        return ActionResult(
            success=True,
            response_text=resp_text,
            spoken_text=spoken,
            intent=command.intent,
            raw_command=command.raw_text
        )

    def _handle_stop(self, command: Command) -> ActionResult:
        """
        Handle 'Stop' interrupt: pauses active media / halts current task.
        Explicitly disambiguated from Exit SYRAX: NEVER closes the application.
        """
        # 1. Stop active media playback via contextual router
        from core.application_controller import get_application_controller
        app_ctrl = get_application_controller()
        app_ctrl.route_context_action("stop")

        spoken = "Playback stopped."
        return ActionResult(
            success=True,
            response_text="Active task / playback stopped.",
            spoken_text=spoken,
            intent=command.intent,
            raw_command=command.raw_text
        )

    def _handle_stop_music(self, command: Command) -> ActionResult:
        from actions.media_actions import MediaActions
        success, msg = MediaActions.pause_playback()
        spoken = "Music stopped."
        return ActionResult(
            success=success,
            response_text="Music playback stopped.",
            spoken_text=spoken,
            intent=command.intent,
            raw_command=command.raw_text
        )

    def _handle_stop_video(self, command: Command) -> ActionResult:
        from actions.youtube_actions import get_youtube_actions
        success, msg = get_youtube_actions().pause()
        spoken = "Video stopped."
        return ActionResult(
            success=success,
            response_text="Video playback stopped.",
            spoken_text=spoken,
            intent=command.intent,
            raw_command=command.raw_text
        )

    def _handle_stop_scrolling(self, command: Command) -> ActionResult:
        spoken = "Scrolling stopped."
        return ActionResult(
            success=True,
            response_text="Scrolling stopped.",
            spoken_text=spoken,
            intent=command.intent,
            raw_command=command.raw_text
        )

    def _handle_cancel_message(self, command: Command) -> ActionResult:
        from actions.whatsapp_actions import get_whatsapp_actions
        success, msg, spoken = get_whatsapp_actions().cancel_pending_message()
        return ActionResult(
            success=success,
            response_text=msg,
            spoken_text=spoken,
            intent=command.intent,
            raw_command=command.raw_text
        )

    def _handle_close_youtube(self, command: Command) -> ActionResult:
        from actions.youtube_actions import get_youtube_actions
        success, msg = get_youtube_actions().close_youtube()
        spoken = "Closed YouTube."
        return ActionResult(
            success=success,
            response_text=msg,
            spoken_text=spoken,
            intent=command.intent,
            raw_command=command.raw_text
        )

    def _handle_close_instagram(self, command: Command) -> ActionResult:
        from actions.instagram_actions import get_instagram_actions
        success, msg = get_instagram_actions().close_instagram()
        spoken = "Closed Instagram."
        return ActionResult(
            success=success,
            response_text=msg,
            spoken_text=spoken,
            intent=command.intent,
            raw_command=command.raw_text
        )

    def _handle_close_whatsapp(self, command: Command) -> ActionResult:
        from actions.whatsapp_actions import get_whatsapp_actions
        success, msg = get_whatsapp_actions().close_whatsapp()
        spoken = "Closed WhatsApp."
        return ActionResult(
            success=success,
            response_text=msg,
            spoken_text=spoken,
            intent=command.intent,
            raw_command=command.raw_text
        )

    def _handle_close_tab(self, command: Command) -> ActionResult:
        success, msg = BrowserActions.close_current_tab()
        spoken = "Closed current tab."
        return ActionResult(
            success=success,
            response_text=msg,
            spoken_text=spoken,
            intent=command.intent,
            raw_command=command.raw_text
        )

    def _handle_close_browser(self, command: Command) -> ActionResult:
        success, msg = BrowserActions.close_all_browser()
        spoken = "Closed managed browser."
        return ActionResult(
            success=success,
            response_text=msg,
            spoken_text=spoken,
            intent=command.intent,
            raw_command=command.raw_text
        )

    def _handle_send_message(self, command: Command) -> ActionResult:
        """Handle drafting and slot-filling for WhatsApp messaging."""
        from actions.whatsapp_actions import get_whatsapp_actions
        wa = get_whatsapp_actions()
        contact = command.target or command.parameters.get("contact")
        message = command.query or command.parameters.get("message")
        success, desc, spoken = wa.start_message_flow(contact=contact, message=message)
        return ActionResult(
            success=success,
            response_text=f"WhatsApp: {desc}",
            spoken_text=spoken,
            intent=command.intent,
            raw_command=command.raw_text
        )

    def _handle_confirmation(self, command: Command) -> ActionResult:
        """Handle confirmation (Yes / No) for pending operations like WhatsApp messages."""
        from actions.whatsapp_actions import get_whatsapp_actions
        wa = get_whatsapp_actions()
        action = command.action or "confirm"
        if action == "confirm":
            success, msg, spoken = wa.execute_confirmed_send()
        else:
            success, msg, spoken = wa.cancel_pending_message()

        return ActionResult(
            success=success,
            response_text=msg,
            spoken_text=spoken,
            intent=command.intent,
            raw_command=command.raw_text
        )

    def _handle_diagnostics(self, command: Command) -> ActionResult:
        spoken = self._pick_response("diagnostics_run")
        return ActionResult(
            success=True,
            response_text="Diagnostics routine requested.",
            spoken_text=spoken,
            intent=command.intent,
            raw_command=command.raw_text
        )

    def _handle_exit(self, command: Command) -> ActionResult:
        spoken = self._pick_response("shutdown")
        # Trigger system shutdown event
        self._event_bus.emit(Events.SHUTDOWN_REQUESTED, reason="Voice/User Command")
        return ActionResult(
            success=True,
            response_text="Shutting down SYRAX...",
            spoken_text=spoken,
            intent=command.intent,
            raw_command=command.raw_text
        )

    def _handle_unknown(self, command: Command) -> ActionResult:
        spoken = self._pick_response("unknown")
        return ActionResult(
            success=False,
            response_text=f"Unrecognized command: '{command.raw_text}'",
            spoken_text=spoken,
            intent=command.intent,
            raw_command=command.raw_text
        )
