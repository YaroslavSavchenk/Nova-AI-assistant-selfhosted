"""
Spotify helper functions — now playing text, track query parsing, playlist utils.
"""

import asyncio
import re

import spotipy

_PLAYLIST_FILLER = {"my", "the", "a", "playlist", "list", "music", "songs", "tracks"}

_LIKED_SONGS_ALIASES = {"liked songs", "liked", "my likes", "saved songs", "saved tracks", "my liked songs"}


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


def _parse_track_query(query: str) -> str:
    """
    Convert natural-language track queries into Spotify field filter syntax.

    Recognises two patterns (case-insensitive):
      - "X by Y"   →  track:X artist:Y
      - "X - Y"    →  track:X artist:Y

    If neither pattern is detected the original query is returned unchanged.
    """
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
