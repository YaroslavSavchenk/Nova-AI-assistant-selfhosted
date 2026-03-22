"""
Spotify module for Nova — search & play, playback control, now playing.

Requires:
  - SPOTIFY_CLIENT_ID in .env
  - SPOTIFY_REDIRECT_URI in .env (http://localhost:8888/callback)
  - Run `python3 scripts/spotify_auth.py` once to authorize and cache the token

Uses spotipy with SpotifyPKCE. Token is cached in data/spotify_token.json.
"""

import asyncio
import logging
import os

import spotipy
from spotipy.oauth2 import SpotifyOAuth

from modules.base import NovaModule

logger = logging.getLogger(__name__)

_SCOPES = " ".join([
    "user-read-playback-state",
    "user-modify-playback-state",
    "user-read-currently-playing",
    "streaming",
    "playlist-read-private",
    "playlist-read-collaborative",
    "user-library-read",
])

_TOKEN_CACHE = "data/spotify_token.json"


def _get_client() -> spotipy.Spotify | None:
    """
    Return an authenticated Spotify client using cached token.
    Returns None if credentials are missing or token is not cached.
    """
    client_id = os.getenv("SPOTIFY_CLIENT_ID", "")
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET", "")
    redirect_uri = os.getenv("SPOTIFY_REDIRECT_URI", "http://localhost:8888/callback")

    if not client_id or not client_secret:
        return None

    auth = SpotifyOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        scope=_SCOPES,
        cache_path=_TOKEN_CACHE,
        open_browser=False,
    )
    return spotipy.Spotify(auth_manager=auth)


def _get_device_id(sp: spotipy.Spotify) -> str | None:
    """Return the active device ID, or the first available device if none is active."""
    devices = sp.devices().get("devices", [])
    if not devices:
        return None
    active = next((d for d in devices if d["is_active"]), None)
    return (active or devices[0])["id"]


_PLAYLIST_FILLER = {"my", "the", "a", "playlist", "list", "music", "songs", "tracks"}


async def _now_playing_text(sp: spotipy.Spotify) -> str:
    """
    Return 'Now playing: X by Y' after a track change.
    Retries up to 3 times (max 1.5 s total) to wait for Spotify to update.
    """
    for _ in range(3):
        try:
            current = sp.current_playback()
            if current and current.get("item"):
                item = current["item"]
                return f"Now playing: {item['name']} by {item['artists'][0]['name']}"
        except Exception:
            break
        await asyncio.sleep(0.5)
    return ""

_LIKED_SONGS_ALIASES = {"liked songs", "liked", "my likes", "saved songs", "saved tracks", "my liked songs"}


def _is_liked_songs_query(query: str) -> bool:
    """Return True if the query refers to the user's Liked Songs collection."""
    return query.lower().strip() in _LIKED_SONGS_ALIASES


def _play_liked_songs(sp: spotipy.Spotify, device_id: str, limit: int = 50) -> str:
    """
    Fetch the user's saved tracks and start playback.
    Returns a result string.
    """
    page = sp.current_user_saved_tracks(limit=limit)
    items = page.get("items", [])
    if not items:
        return "You have no liked/saved tracks on Spotify."
    uris = [item["track"]["uri"] for item in items if item.get("track")]
    sp.start_playback(device_id=device_id, uris=uris)
    return f"Now playing your Liked Songs ({len(uris)} tracks shuffled from your library)."


def _fetch_all_user_playlists(sp: spotipy.Spotify) -> list[dict]:
    """Fetch all playlists the user owns or follows (paginated)."""
    results = []
    offset = 0
    while True:
        page = sp.current_user_playlists(limit=50, offset=offset)
        items = page.get("items", [])
        if not items:
            break
        results.extend(items)
        if page.get("next") is None:
            break
        offset += 50
    return results


def _clean_playlist_query(query: str) -> str:
    """Strip filler words so 'my Car playlist' → 'car' for matching."""
    words = [w for w in query.lower().split() if w not in _PLAYLIST_FILLER]
    return " ".join(words).strip() or query.lower().strip()


def _find_user_playlist(sp: spotipy.Spotify, query: str) -> dict | None:
    """
    Search the user's own playlists (created + saved/followed) for a name match.

    Matching order (tried on both raw query and filler-stripped query):
    1. Exact name match
    2. Playlist name contained in query ("my Gym playlist" → "Gym")
    3. Query contained in playlist name ("gym" → "Gym Motivation")
    4. Word-level overlap (ignoring filler words)
    """
    playlists = _fetch_all_user_playlists(sp)
    raw = query.lower().strip()
    clean = _clean_playlist_query(query)

    for q in dict.fromkeys([raw, clean]):  # try raw first, then deduped clean
        # 1. Exact match
        exact = next((p for p in playlists if p["name"].lower() == q), None)
        if exact:
            return exact

        # 2. Playlist name contained in query
        by_name_in_query = next((p for p in playlists if p["name"].lower() in q), None)
        if by_name_in_query:
            return by_name_in_query

        # 3. Query contained in playlist name
        by_query_in_name = next((p for p in playlists if q in p["name"].lower()), None)
        if by_query_in_name:
            return by_query_in_name

    # 4. Word-level match on cleaned query words
    clean_words = set(clean.split()) - _PLAYLIST_FILLER
    if clean_words:
        for p in playlists:
            name_words = set(p["name"].lower().split())
            if clean_words & name_words:
                return p

    return None


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


class SpotifyMyPlaylistsModule(NovaModule):
    """List the user's Spotify playlists, grouped by created vs saved."""

    name: str = "spotify_my_playlists"
    description: str = (
        "List the user's Spotify playlists — both playlists they created and ones they saved/followed. "
        "Use this when the user asks 'what playlists do I have', 'show my playlists', or wants to find a specific playlist by name."
    )
    parameters: dict = {
        "type": "object",
        "properties": {
            "filter": {
                "type": "string",
                "description": "Filter to show: 'all' (default), 'mine' (only created by user), or 'saved' (only followed/saved from others).",
            },
        },
        "required": [],
    }

    async def run(self, **kwargs) -> str:
        try:
            sp = _get_client()
            if sp is None:
                return "Spotify is not configured. Run `python3 scripts/spotify_auth.py` first."

            filter_type: str = kwargs.get("filter", "all").lower()
            user_id = sp.current_user()["id"]
            playlists = _fetch_all_user_playlists(sp)

            owned = [p for p in playlists if p["owner"]["id"] == user_id]
            saved = [p for p in playlists if p["owner"]["id"] != user_id]

            # Get liked songs count for 'all' and 'saved' views
            liked_count = None
            if filter_type in ("all", "saved"):
                liked_page = sp.current_user_saved_tracks(limit=1)
                liked_count = liked_page.get("total", 0)

            if filter_type == "mine":
                selected = owned
                label = "Your created playlists"
            elif filter_type == "saved":
                selected = saved
                label = "Playlists you saved/followed"
            else:
                selected = playlists
                label = "Your Spotify playlists"

            if not selected and liked_count == 0:
                return f"No playlists found (filter: {filter_type})."

            lines = [f"{label} ({len(selected)} total):\n"]
            if filter_type == "all":
                lines.append(f"  ♥ Liked Songs ({liked_count} tracks) — say 'play my liked songs'")
                if owned:
                    lines.append("\nCreated by you:")
                    for p in owned:
                        lines.append(f"  • {p['name']} ({p['tracks']['total']} tracks)")
                if saved:
                    lines.append("\nSaved/followed:")
                    for p in saved:
                        lines.append(f"  • {p['name']} by {p['owner']['display_name'] or p['owner']['id']} ({p['tracks']['total']} tracks)")
            elif filter_type == "saved":
                lines.append(f"  ♥ Liked Songs ({liked_count} tracks)")
                for p in selected:
                    lines.append(f"  • {p['name']} ({p['tracks']['total']} tracks)")
            else:
                for p in selected:
                    lines.append(f"  • {p['name']} ({p['tracks']['total']} tracks)")

            return "\n".join(lines)

        except spotipy.exceptions.SpotifyException as exc:
            logger.exception("SpotifyMyPlaylistsModule error")
            return f"Spotify error: {exc}"
        except Exception as exc:
            logger.exception("SpotifyMyPlaylistsModule error")
            return f"Failed to get playlists: {exc}"


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


def _parse_track_query(query: str) -> str:
    """
    Convert natural-language track queries into Spotify field filter syntax.

    Recognises two patterns (case-insensitive):
      - "X by Y"   →  track:X artist:Y
      - "X - Y"    →  track:X artist:Y

    If neither pattern is detected the original query is returned unchanged.
    """
    import re

    # "Title by Artist" — require at least one non-space char on each side
    m = re.match(r'^(.+?)\s+by\s+(.+)$', query, re.IGNORECASE)
    if m:
        track_part = m.group(1).strip()
        artist_part = m.group(2).strip()
        return f"track:{track_part} artist:{artist_part}"

    # "Title - Artist"
    m = re.match(r'^(.+?)\s+-\s+(.+)$', query)
    if m:
        track_part = m.group(1).strip()
        artist_part = m.group(2).strip()
        return f"track:{track_part} artist:{artist_part}"

    return query


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
            if not queue:
                lines.append("Queue is empty — nothing coming up next.")
            else:
                # Spotify returns explicitly queued tracks first, then album/context
                # autofill tracks. Show only the first 5 to avoid noise.
                display = queue[:5]
                lines.append(f"\nUp next:")
                for i, track in enumerate(display, 1):
                    name = track.get("name", "Unknown")
                    artist = track.get("artists", [{}])[0].get("name", "Unknown")
                    lines.append(f"  {i}. {name} by {artist}")
                if len(queue) > 5:
                    lines.append(f"  (+ {len(queue) - 5} more from album/autoplay)")

            return "\n".join(lines)

        except spotipy.exceptions.SpotifyException as exc:
            logger.exception("SpotifyViewQueueModule error")
            return f"Spotify error: {exc}"
        except Exception as exc:
            logger.exception("SpotifyViewQueueModule error")
            return f"Failed to get queue: {exc}"
