"""SpotifyControlModule and SpotifySkipToModule — playback control."""

import asyncio
import logging

import spotipy

from modules.base import NovaModule
from ._client import _get_client, _get_device_id
from ._helpers import _now_playing_text

logger = logging.getLogger(__name__)


class SpotifyControlModule(NovaModule):
    """Control Spotify playback — pause, resume, skip, previous, volume, shuffle."""

    name: str = "spotify_control"
    description: str = (
        "Control Spotify playback. MUST be called for any playback action — never simulate or assume the result. "
        "Never respond with text describing a skip, pause, or resume — always call this tool first, then respond with the actual result. "
        "Use this to: pause, resume, skip, skip song, next song, next track, go to next, go forward, "
        "previous song, previous track, go back, go to previous, set volume, change volume, "
        "turn shuffle on/off, or toggle shuffle. "
        "To skip multiple songs at once (e.g. 'go straight to X', 'skip 3 songs'), use action='next' with count > 1. "
        "Trigger phrases that require this tool: 'skip', 'next', 'next song', 'skip song', "
        "'skip this', 'skip track', 'go to next', 'go forward', 'previous', 'go back', 'last song', "
        "'pause', 'pause this', 'stop music', 'resume', 'continue', 'unpause', "
        "'volume up', 'volume down', 'set volume', 'louder', 'quieter', 'shuffle', 'turn on shuffle', 'turn off shuffle'. "
        "Do not say 'I'll skip now' or 'Skipping...' — call this tool and report what it returns."
    )
    parameters: dict = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": (
                    "Action to perform. Allowed values: 'pause', 'resume', 'next', 'previous', 'volume', 'shuffle'. "
                    "Use 'next' to skip forward (use count to skip multiple songs at once). "
                    "Use 'previous' to go back or replay the previous song. "
                    "Use 'resume' to continue playback. "
                    "Use 'pause' to stop playback. "
                    "Use 'volume' with the volume parameter to set loudness. "
                    "Use 'shuffle' with the state parameter to enable, disable, or toggle shuffle."
                ),
            },
            "count": {
                "type": "integer",
                "description": (
                    "Number of tracks to skip. Only used when action is 'next'. Defaults to 1. "
                    "Use this when the user wants to jump multiple songs — e.g. 'skip 3 songs' → count=3, "
                    "'go straight to X' when X is 2 songs ahead → count=2."
                ),
            },
            "volume": {
                "type": "integer",
                "description": "Volume level 0-100. Only used when action is 'volume'.",
            },
            "state": {
                "type": "string",
                "description": "For shuffle: 'on', 'off', or 'toggle' (default). Only used when action is 'shuffle'.",
            },
        },
        "required": ["action"],
    }

    async def run(self, **kwargs) -> str:
        try:
            action: str = kwargs.get("action", "").lower().strip()
            if not action:
                return "Error: action cannot be empty."

            sp = _get_client()
            if sp is None:
                return "Spotify is not configured. Run `python3 scripts/spotify_auth.py` first."

            device_id = _get_device_id(sp)
            if device_id is None:
                return "No Spotify device found. Open Spotify on your PC first."

            if action == "pause":
                sp.pause_playback(device_id=device_id)
                return "Spotify paused."

            elif action in ("resume", "play"):
                sp.start_playback(device_id=device_id)
                return "Spotify resumed."

            elif action == "next":
                count = max(1, int(kwargs.get("count", 1)))
                for _ in range(count):
                    sp.next_track(device_id=device_id)
                    if count > 1:
                        await asyncio.sleep(0.3)
                label = f"Skipped {count} tracks." if count > 1 else "Skipped."
                return label + " " + await _now_playing_text(sp)

            elif action == "previous":
                sp.previous_track(device_id=device_id)
                return "Went back. " + await _now_playing_text(sp)

            elif action == "volume":
                level = int(kwargs.get("volume", 50))
                level = max(0, min(100, level))
                sp.volume(level, device_id=device_id)
                return f"Volume set to {level}%."

            elif action == "shuffle":
                state: str = kwargs.get("state", "toggle").lower().strip()
                if state == "on":
                    enabled = True
                elif state == "off":
                    enabled = False
                else:
                    # Toggle: check current playback state
                    playback = sp.current_playback()
                    current = playback.get("shuffle_state", False) if playback else False
                    enabled = not current
                sp.shuffle(enabled, device_id=device_id)
                return f"Shuffle {'enabled' if enabled else 'disabled'}."

            else:
                return f"Unknown action '{action}'. Valid actions: pause, resume, next, previous, volume, shuffle."

        except spotipy.exceptions.SpotifyException as exc:
            if exc.http_status == 403:
                return "Spotify playback control requires a Premium account."
            if exc.http_status == 404:
                return "No active Spotify device found. Open Spotify on your PC or phone first."
            logger.exception("SpotifyControlModule error")
            return f"Spotify error: {exc}"
        except Exception as exc:
            logger.exception("SpotifyControlModule error")
            return f"Spotify control failed: {exc}"


class SpotifySkipToModule(NovaModule):
    """Skip directly to a specific track in the queue by name."""

    name: str = "spotify_skip_to"
    description: str = (
        "Skip directly to a specific song already in the queue by name. "
        "Use this instead of spotify_control when the user says 'skip to X', "
        "'go straight to X', 'jump to X', or 'play X from the queue'. "
        "Reads the current queue, finds the song's position, and skips exactly "
        "the right number of times — no guessing required."
    )
    parameters: dict = {
        "type": "object",
        "properties": {
            "track_name": {
                "type": "string",
                "description": "Name of the track to skip to — e.g. 'Manic' or 'Him and I'.",
            },
        },
        "required": ["track_name"],
    }

    async def run(self, **kwargs) -> str:
        try:
            target: str = kwargs.get("track_name", "").strip().lower()
            if not target:
                return "Error: track name cannot be empty."

            sp = _get_client()
            if sp is None:
                return "Spotify is not configured. Run `python3 scripts/spotify_auth.py` first."

            device_id = _get_device_id(sp)
            if device_id is None:
                return "No Spotify device found. Open Spotify on your PC first."

            queue_data = sp.queue()
            if not queue_data:
                return "No active playback."

            queue = queue_data.get("queue", [])
            if not queue:
                return "Queue is empty — nothing to skip to."

            def _normalize(s: str) -> str:
                """Lowercase and replace & with 'and' for fuzzy matching."""
                return s.lower().replace("&", "and").replace("  ", " ").strip()

            target_norm = _normalize(target)

            # Find the target track (name contains query or query contains name)
            position = None
            found_name = None
            found_artist = None
            for i, track in enumerate(queue):
                name = _normalize(track.get("name", ""))
                if target_norm in name or name in target_norm:
                    position = i + 1  # number of next_track calls needed
                    found_name = track.get("name")
                    found_artist = track.get("artists", [{}])[0].get("name", "")
                    break

            if position is None:
                available = [
                    f"{t.get('name')} by {t.get('artists', [{}])[0].get('name', '')}"
                    for t in queue[:5]
                ]
                return (
                    f"'{kwargs.get('track_name')}' not found in queue. "
                    f"Up next: {', '.join(available)}"
                )

            for _ in range(position):
                sp.next_track(device_id=device_id)
                if position > 1:
                    await asyncio.sleep(0.4)

            label = f"Skipped {position} track{'s' if position > 1 else ''}."
            return f"{label} Now playing: {found_name} by {found_artist}"

        except spotipy.exceptions.SpotifyException as exc:
            if exc.http_status == 403:
                return "Spotify Premium required for skip."
            if exc.http_status == 404:
                return "No active Spotify device found."
            logger.exception("SpotifySkipToModule error")
            return f"Spotify error: {exc}"
        except Exception as exc:
            logger.exception("SpotifySkipToModule error")
            return f"Skip-to failed: {exc}"
