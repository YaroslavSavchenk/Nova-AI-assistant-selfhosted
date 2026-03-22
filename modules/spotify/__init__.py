"""
modules.spotify — Spotify integration package for Nova.

Re-exports all public classes for backward-compatible imports:
    from modules.spotify import SpotifyPlayModule, SpotifyControlModule, ...
"""

from .play import SpotifyPlayModule
from .control import SpotifyControlModule, SpotifySkipToModule
from .now_playing import SpotifyNowPlayingModule
from .queue import SpotifyQueueModule, SpotifyViewQueueModule
from .playlists import SpotifyMyPlaylistsModule
from .lyrics_search import SpotifyLyricsSearchModule

# Re-export internal helpers so external patches (e.g. in tests) can target
# modules.spotify._get_client and modules.spotify._now_playing_text.
from ._client import _get_client, _get_device_id
from ._helpers import _now_playing_text

__all__ = [
    "SpotifyPlayModule",
    "SpotifyControlModule",
    "SpotifySkipToModule",
    "SpotifyNowPlayingModule",
    "SpotifyQueueModule",
    "SpotifyViewQueueModule",
    "SpotifyMyPlaylistsModule",
    "SpotifyLyricsSearchModule",
    "_get_client",
    "_get_device_id",
    "_now_playing_text",
]
