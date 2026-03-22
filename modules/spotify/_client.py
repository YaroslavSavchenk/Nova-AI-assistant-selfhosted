"""
Spotify client factory — authentication and device helpers.

All other spotify submodules import _get_client and _get_device_id from here.
"""

import os

import spotipy
from spotipy.oauth2 import SpotifyOAuth

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
