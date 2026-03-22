"""SpotifyPlayModule — search Spotify and play a track, artist, album, or playlist."""

import logging

import spotipy

from modules.base import NovaModule
from ._client import _get_client, _get_device_id
from ._helpers import _parse_track_query, _is_liked_songs_query, _play_liked_songs, _find_user_playlist

logger = logging.getLogger(__name__)


class SpotifyPlayModule(NovaModule):
    """Search Spotify and play a track, artist, album, or playlist."""

    name: str = "spotify_play"
    description: str = (
        "Search Spotify and start playing a track, artist, album, or playlist. "
        "Use this when the user wants to play or listen to music."
    )
    parameters: dict = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "What to play — e.g. 'Arctic Monkeys', 'Bohemian Rhapsody', 'chill playlist'",
            },
            "type": {
                "type": "string",
                "description": "Type of result to search for: 'track', 'artist', 'album', or 'playlist'. Defaults to 'track'.",
            },
        },
        "required": ["query"],
    }

    async def run(self, **kwargs) -> str:
        try:
            query: str = kwargs.get("query", "").strip()
            if not query:
                return "Error: search query cannot be empty."

            search_type: str = kwargs.get("type", "track").lower()
            if search_type not in ("track", "artist", "album", "playlist"):
                search_type = "track"

            sp = _get_client()
            if sp is None:
                return "Spotify is not configured. Run `python3 scripts/spotify_auth.py` first."

            device_id = _get_device_id(sp)
            if device_id is None:
                return "No Spotify device found. Open Spotify on your PC first."

            if search_type == "track":
                search_query = _parse_track_query(query)
                results = sp.search(q=search_query, type="track", limit=1)
                items = results.get("tracks", {}).get("items", [])
                if not items:
                    return f"No track found for: {query}"
                item = items[0]
                # Play via album context + offset so Spotify's queue system works
                # correctly. Playing with uris=[single_uri] puts Spotify in a
                # no-context mode that breaks add_to_queue and skip.
                album_uri = item.get("album", {}).get("uri")
                if album_uri:
                    sp.start_playback(
                        device_id=device_id,
                        context_uri=album_uri,
                        offset={"uri": item["uri"]},
                    )
                else:
                    # Fallback for tracks without an album (rare)
                    sp.start_playback(device_id=device_id, uris=[item["uri"]])
                return f"Now playing: {item['name']} by {item['artists'][0]['name']}"

            elif search_type == "artist":
                # Use artist: prefix for precise match
                results = sp.search(q=f"artist:{query}", type="artist", limit=1)
                items = results.get("artists", {}).get("items", [])
                if not items:
                    return f"No artist found for: {query}"
                artist_name = items[0]["name"]
                track_results = sp.search(q=f"artist:{artist_name}", type="track", limit=10)
                tracks = track_results.get("tracks", {}).get("items", [])
                if not tracks:
                    return f"No tracks found for artist: {artist_name}"
                sp.start_playback(device_id=device_id, uris=[t["uri"] for t in tracks])
                return f"Now playing top tracks by {artist_name}"

            elif search_type == "album":
                results = sp.search(q=query, type="album", limit=1)
                items = results.get("albums", {}).get("items", [])
                if not items:
                    return f"No album found for: {query}"
                item = items[0]
                sp.start_playback(device_id=device_id, context_uri=item["uri"])
                return f"Now playing album: {item['name']} by {item['artists'][0]['name']}"

            elif search_type == "playlist":
                # Handle "Liked Songs" as a special case
                if _is_liked_songs_query(query):
                    return _play_liked_songs(sp, device_id)

                # Check user's own playlists first, then fall back to public search
                user_playlist = _find_user_playlist(sp, query)
                if user_playlist:
                    sp.start_playback(device_id=device_id, context_uri=user_playlist["uri"])
                    sp.shuffle(False, device_id=device_id)
                    return f"Now playing your playlist: {user_playlist['name']}"
                results = sp.search(q=query, type="playlist", limit=1)
                items = results.get("playlists", {}).get("items", [])
                if not items:
                    return f"No playlist found for: {query}"
                item = items[0]
                sp.start_playback(device_id=device_id, context_uri=item["uri"])
                sp.shuffle(False, device_id=device_id)
                return f"Now playing playlist: {item['name']}"

        except spotipy.exceptions.SpotifyException as exc:
            if exc.http_status == 403 and "playback" in str(exc).lower():
                return "Spotify playback control requires a Premium account."
            if exc.http_status == 403:
                return f"Spotify API returned 403 Forbidden: {exc}"
            if exc.http_status == 404:
                return "No active Spotify device found. Open Spotify on your PC or phone first."
            logger.exception("SpotifyPlayModule error")
            return f"Spotify error: {exc}"
        except Exception as exc:
            logger.exception("SpotifyPlayModule error")
            return f"Spotify play failed: {exc}"
