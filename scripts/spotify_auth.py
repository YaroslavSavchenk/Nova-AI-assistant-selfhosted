"""
One-time Spotify OAuth authorization script.

Run this once to authenticate Nova with your Spotify account:
    python3 scripts/spotify_auth.py
"""

import logging
import os
import sys
from pathlib import Path

logging.getLogger("spotipy").setLevel(logging.CRITICAL)
logging.getLogger("spotipy.oauth2").setLevel(logging.CRITICAL)

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

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


def main() -> None:
    client_id = os.getenv("SPOTIFY_CLIENT_ID", "")
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET", "")
    redirect_uri = os.getenv("SPOTIFY_REDIRECT_URI", "https://yaroslavsavchenk.github.io/spotify-callback/")

    if not client_id:
        print("ERROR: SPOTIFY_CLIENT_ID must be set in .env")
        sys.exit(1)
    if not client_secret:
        print("ERROR: SPOTIFY_CLIENT_SECRET must be set in .env")
        sys.exit(1)

    auth = SpotifyOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        scope=_SCOPES,
        cache_path=_TOKEN_CACHE,
        open_browser=False,
    )

    auth_url = auth.get_authorize_url()

    print("Open this URL in your Windows browser:")
    print()
    print(auth_url)
    print()
    print("After logging in, you will be redirected to a callback URL.")
    print("Copy the FULL redirect URL from the browser address bar and paste it below.")
    print()

    redirected_url = input("Paste the full redirect URL here:\n> ").strip()

    if not redirected_url:
        print("ERROR: No URL entered.")
        sys.exit(1)

    code = auth.parse_response_code(redirected_url)
    token_info = auth.get_access_token(code)

    if token_info:
        print(f"\nAuthorization successful! Token cached at: {_TOKEN_CACHE}")
        print("You can now use Spotify commands in Nova.")
    else:
        print("\nAuthorization failed. Check your credentials and try again.")
        sys.exit(1)


if __name__ == "__main__":
    main()
