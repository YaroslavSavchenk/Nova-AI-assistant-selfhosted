"""SpotifyQueueModule and SpotifyViewQueueModule — queue management."""

import logging

import spotipy

from modules.base import NovaModule
from ._client import _get_client
from ._helpers import _parse_track_query

logger = logging.getLogger(__name__)


class SpotifyQueueModule(NovaModule):
    """Add a track to the Spotify playback queue."""

    name: str = "spotify_queue"
    description: str = (
        "Add a track to the Spotify playback queue. "
        "MUST be called when the user asks to queue a song — never confirm a track was queued without calling this tool first. "
        "Always call this tool when the user says 'queue', 'add to queue', 'add X to queue', "
        "'put X in the queue', or 'play X next' without stopping the current song. "
        "Do not say 'Added X to queue' without calling this tool and reporting its actual result."
    )
    parameters: dict = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Track to queue — e.g. 'Bohemian Rhapsody' or 'Stairway to Heaven by Led Zeppelin'",
            },
        },
        "required": ["query"],
    }

    async def run(self, **kwargs) -> str:
        try:
            query: str = kwargs.get("query", "").strip()
            if not query:
                return "Error: query cannot be empty."

            sp = _get_client()
            if sp is None:
                return "Spotify is not configured. Run `python3 scripts/spotify_auth.py` first."

            search_query = _parse_track_query(query)
            results = sp.search(q=search_query, type="track", limit=1)
            items = results.get("tracks", {}).get("items", [])
            if not items:
                return f"No track found for: {query}"

            track = items[0]
            sp.add_to_queue(track["uri"])
            return f"Queued: {track['name']} by {track['artists'][0]['name']}"

        except spotipy.exceptions.SpotifyException as exc:
            if exc.http_status == 403:
                return "Spotify queue requires a Premium account."
            if exc.http_status == 404:
                return "No active Spotify device found. Open Spotify on your PC or phone first."
            logger.exception("SpotifyQueueModule error")
            return f"Spotify error: {exc}"
        except Exception as exc:
            logger.exception("SpotifyQueueModule error")
            return f"Failed to queue track: {exc}"


class SpotifyViewQueueModule(NovaModule):
    """View the current Spotify playback queue."""

    name: str = "spotify_view_queue"
    description: str = (
        "Show what's coming up in the Spotify queue. Use this when the user asks "
        "'what's in the queue', 'what's next', 'show my queue', or wants to manage upcoming tracks."
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

            data = sp.queue()
            if not data:
                return "Nothing is currently playing on Spotify."

            lines = []

            current = data.get("currently_playing")
            if current:
                name = current.get("name", "Unknown")
                artist = current.get("artists", [{}])[0].get("name", "Unknown")
                lines.append(f"Now playing: {name} by {artist}")

            queue = data.get("queue", [])

            # Deduplicate: collapse consecutive or repeated same-name+artist entries
            # (album autoplay often queues many versions of the same track).
            # Also filter out copies of the currently playing track.
            current_key = None
            if current:
                current_key = (
                    current.get("name", "").lower(),
                    current.get("artists", [{}])[0].get("name", "").lower(),
                )
            seen: dict[tuple, int] = {}
            deduped = []
            for track in queue:
                name = track.get("name", "Unknown")
                artist = track.get("artists", [{}])[0].get("name", "Unknown")
                key = (name.lower(), artist.lower())
                if key == current_key:
                    continue  # album autoplay copy of currently playing song
                if key in seen:
                    seen[key] += 1
                else:
                    seen[key] = 1
                    deduped.append(track)

            if not deduped:
                lines.append("Queue is empty — nothing coming up next.")
            else:
                lines.append("\nUp next:")
                for i, track in enumerate(deduped[:5], 1):
                    name = track.get("name", "Unknown")
                    artist = track.get("artists", [{}])[0].get("name", "Unknown")
                    key = (name.lower(), artist.lower())
                    count = seen.get(key, 1)
                    suffix = f" (×{count})" if count > 1 else ""
                    lines.append(f"  {i}. {name} by {artist}{suffix}")
                hidden = len(deduped) - 5
                if hidden > 0:
                    lines.append(f"  (+ {hidden} more from album/autoplay)")

            return "\n".join(lines)

        except spotipy.exceptions.SpotifyException as exc:
            logger.exception("SpotifyViewQueueModule error")
            return f"Spotify error: {exc}"
        except Exception as exc:
            logger.exception("SpotifyViewQueueModule error")
            return f"Failed to get queue: {exc}"
