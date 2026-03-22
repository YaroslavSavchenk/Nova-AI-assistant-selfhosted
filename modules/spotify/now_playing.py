"""SpotifyNowPlayingModule — get the currently playing Spotify track."""

import logging

import spotipy

from modules.base import NovaModule
from ._client import _get_client

logger = logging.getLogger(__name__)


class SpotifyNowPlayingModule(NovaModule):
    """Get the currently playing Spotify track."""

    name: str = "spotify_now_playing"
    description: str = (
        "Get information about the currently playing Spotify track. "
        "Use this when the user asks 'what's playing', 'what song is this', or similar."
    )
    parameters: dict = {
        "type": "object",
        "properties": {},
        "required": [],
    }

    async def run(self, **kwargs) -> str:
        try:
            sp = _get_client()
            if sp is None:
                return "Spotify is not configured. Run `python3 scripts/spotify_auth.py` first."

            current = sp.current_playback()
            if not current or not current.get("item"):
                return "Nothing is currently playing on Spotify."

            item = current["item"]
            track = item["name"]
            artists = ", ".join(a["name"] for a in item["artists"])
            album = item["album"]["name"]
            is_playing = current.get("is_playing", False)
            progress_ms = current.get("progress_ms", 0)
            duration_ms = item.get("duration_ms", 0)

            progress = f"{progress_ms // 60000}:{(progress_ms // 1000) % 60:02d}"
            duration = f"{duration_ms // 60000}:{(duration_ms // 1000) % 60:02d}"
            status = "Playing" if is_playing else "Paused"

            return (
                f"{status}: {track} by {artists}\n"
                f"Album: {album}\n"
                f"Progress: {progress} / {duration}"
            )

        except spotipy.exceptions.SpotifyException as exc:
            logger.exception("SpotifyNowPlayingModule error")
            return f"Spotify error: {exc}"
        except Exception as exc:
            logger.exception("SpotifyNowPlayingModule error")
            return f"Failed to get now playing: {exc}"
