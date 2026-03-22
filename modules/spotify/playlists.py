"""SpotifyMyPlaylistsModule — list user playlists."""

import logging

import spotipy

from modules.base import NovaModule
from ._client import _get_client
from ._helpers import _fetch_all_user_playlists

logger = logging.getLogger(__name__)


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
