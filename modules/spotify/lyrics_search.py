"""
SpotifyLyricsSearchModule — identify songs from lyric snippets.

Uses the Genius API to search for songs matching a lyric fragment. Returns the
top candidates for the user to confirm, then Nova calls spotify_play to play it.

Requires:
  - GENIUS_ACCESS_TOKEN in .env
  - Register at https://genius.com/api-clients (free)
"""

import logging
import os

import httpx

from modules.base import NovaModule

logger = logging.getLogger(__name__)

_GENIUS_SEARCH_URL = "https://api.genius.com/search"
_HTTP_TIMEOUT = 10


class SpotifyLyricsSearchModule(NovaModule):
    """Identify a song from a lyric snippet using the Genius API."""

    name: str = "spotify_lyrics_search"
    description: str = (
        "Identify a song from a lyric snippet or partial lyrics. Use this when the user "
        "says a line from a song but doesn't know the title or artist — e.g. "
        "'that song that goes is this the real life' or 'play the one with we will rock you'. "
        "Returns the top matching song(s) for the user to confirm. "
        "After the user confirms, call spotify_play with the full 'Title by Artist' string "
        "as the query and type set to 'track' — e.g. query='Bohemian Rhapsody by Queen', type='track'."
    )
    parameters: dict = {
        "type": "object",
        "properties": {
            "lyrics": {
                "type": "string",
                "description": (
                    "The lyric snippet to search for — e.g. "
                    "'is this the real life is this just fantasy'"
                ),
            },
        },
        "required": ["lyrics"],
    }

    async def run(self, **kwargs) -> str:
        try:
            lyrics: str = kwargs.get("lyrics", "").strip()
            if not lyrics:
                return "Error: lyrics snippet cannot be empty."

            token = os.getenv("GENIUS_ACCESS_TOKEN", "")
            if not token:
                return (
                    "Genius API is not configured. "
                    "Add GENIUS_ACCESS_TOKEN to .env (get one free at genius.com/api-clients)."
                )

            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
                response = await client.get(
                    _GENIUS_SEARCH_URL,
                    params={"q": lyrics},
                    headers={"Authorization": f"Bearer {token}"},
                )
                response.raise_for_status()
                data = response.json()

            hits = data.get("response", {}).get("hits", [])
            if not hits:
                return f'No songs found matching those lyrics: "{lyrics}"'

            candidates = []
            for hit in hits[:3]:
                result = hit.get("result", {})
                title = result.get("title", "Unknown")
                artist = result.get("primary_artist", {}).get("name", "Unknown")
                candidates.append(f"{title} by {artist}")

            if len(candidates) == 1:
                return (
                    f"I found one match: {candidates[0]}. "
                    "Is that the song you're looking for? Say yes and I'll play it."
                )

            lines = ["I found a few matches — which one did you mean?\n"]
            for i, candidate in enumerate(candidates, 1):
                lines.append(f"{i}. {candidate}")
            lines.append("\nSay the number or name and I'll play it.")
            return "\n".join(lines)

        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 401:
                return "Genius API token is invalid or expired. Check GENIUS_ACCESS_TOKEN in .env."
            logger.exception("Genius API HTTP error")
            return f"Genius API error: {exc.response.status_code}"
        except httpx.RequestError as exc:
            logger.exception("Genius API request error")
            return f"Network error contacting Genius API: {exc}"
        except Exception as exc:
            logger.exception("SpotifyLyricsSearchModule error")
            return f"Lyrics search failed: {exc}"
