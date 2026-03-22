"""
Tests for modules/spotify.py — SpotifyPlayModule, SpotifyControlModule,
SpotifyNowPlayingModule, SpotifyMyPlaylistsModule.
"""

import pytest
from unittest.mock import patch, MagicMock

from modules.spotify import (
    SpotifyPlayModule, SpotifyControlModule, SpotifyNowPlayingModule,
    SpotifyMyPlaylistsModule, SpotifyQueueModule,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def play_module():
    return SpotifyPlayModule()


@pytest.fixture
def control_module():
    return SpotifyControlModule()


@pytest.fixture
def now_playing_module():
    return SpotifyNowPlayingModule()


@pytest.fixture
def my_playlists_module():
    return SpotifyMyPlaylistsModule()


@pytest.fixture
def queue_module():
    return SpotifyQueueModule()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_sp():
    """Return a mock spotipy.Spotify client with a default active device."""
    sp = MagicMock()
    sp.devices.return_value = {
        "devices": [{"id": "test-device-id", "is_active": True}]
    }
    return sp


def _fake_track_search(name="Bohemian Rhapsody", artist="Queen", uri="spotify:track:abc123"):
    return {
        "tracks": {
            "items": [{
                "uri": uri,
                "name": name,
                "artists": [{"name": artist}],
            }]
        }
    }


def _fake_artist_track_fill(artist="Queen", playing_uri="spotify:track:abc123"):
    """Return a fake search result with 6 tracks (including the currently playing one)."""
    tracks = [
        {"uri": playing_uri, "name": "Playing Track", "artists": [{"name": artist}]},
    ]
    for i in range(1, 6):
        tracks.append({"uri": f"spotify:track:fill{i}", "name": f"Fill Track {i}", "artists": [{"name": artist}]})
    return {"tracks": {"items": tracks}}


def _fake_artist_search(name="Arctic Monkeys", artist_id="artist123"):
    return {
        "artists": {
            "items": [{
                "id": artist_id,
                "name": name,
            }]
        }
    }


def _fake_album_search(name="AM", artist="Arctic Monkeys", uri="spotify:album:xyz"):
    return {
        "albums": {
            "items": [{
                "uri": uri,
                "name": name,
                "artists": [{"name": artist}],
            }]
        }
    }


def _fake_playlist_search(name="Chill Vibes", uri="spotify:playlist:ppp"):
    return {
        "playlists": {
            "items": [{
                "uri": uri,
                "name": name,
            }]
        }
    }


def _fake_user_playlists(user_id="user123"):
    """Return a mock current_user_playlists page with one owned and one saved playlist."""
    return {
        "items": [
            {
                "name": "My Workout Mix",
                "uri": "spotify:playlist:owned1",
                "owner": {"id": user_id, "display_name": "Me"},
                "tracks": {"total": 20},
            },
            {
                "name": "Indie Discovers",
                "uri": "spotify:playlist:saved1",
                "owner": {"id": "someoneelse", "display_name": "Spotify"},
                "tracks": {"total": 50},
            },
        ],
        "next": None,
    }


def _fake_saved_tracks(total=123):
    return {"total": total, "items": [
        {"track": {"uri": f"spotify:track:{i}", "name": f"Song {i}", "artists": [{"name": "Artist"}]}}
        for i in range(min(total, 5))
    ]}


def _fake_now_playing(track="Bohemian Rhapsody", artist="Queen", album="A Night at the Opera",
                      is_playing=True, progress_ms=90000, duration_ms=360000):
    return {
        "is_playing": is_playing,
        "progress_ms": progress_ms,
        "item": {
            "name": track,
            "artists": [{"name": artist}],
            "album": {"name": album},
            "duration_ms": duration_ms,
        }
    }


# ---------------------------------------------------------------------------
# SpotifyPlayModule tests
# ---------------------------------------------------------------------------


async def test_play_track_success(play_module):
    sp = _mock_sp()
    # First call: track search. Second call: artist fill search.
    sp.search.side_effect = [
        _fake_track_search(),
        _fake_artist_track_fill(),
    ]

    with patch("modules.spotify._get_client", return_value=sp):
        result = await play_module.run(query="Bohemian Rhapsody", type="track")

    sp.start_playback.assert_called_once()
    assert "Bohemian Rhapsody" in result
    assert "Queen" in result


async def test_play_track_queues_artist_fill(play_module):
    """After playing a single track, up to 5 other tracks by the same artist are queued."""
    sp = _mock_sp()
    playing_uri = "spotify:track:abc123"
    sp.search.side_effect = [
        _fake_track_search(uri=playing_uri),
        _fake_artist_track_fill(artist="Queen", playing_uri=playing_uri),
    ]

    with patch("modules.spotify._get_client", return_value=sp):
        result = await play_module.run(query="Bohemian Rhapsody", type="track")

    # Exactly 5 fill tracks should be queued (the 6th result is the playing track, excluded)
    assert sp.add_to_queue.call_count == 5
    queued_uris = [call.args[0] for call in sp.add_to_queue.call_args_list]
    assert playing_uri not in queued_uris
    assert "Bohemian Rhapsody" in result


async def test_play_track_queue_fill_failure_silent(play_module):
    """If add_to_queue raises (e.g. non-Premium), the error is silently ignored."""
    sp = _mock_sp()
    sp.search.side_effect = [
        _fake_track_search(),
        _fake_artist_track_fill(),
    ]
    sp.add_to_queue.side_effect = RuntimeError("Premium required")

    with patch("modules.spotify._get_client", return_value=sp):
        result = await play_module.run(query="Bohemian Rhapsody", type="track")

    # Main response is unaffected
    assert "Bohemian Rhapsody" in result
    assert "error" not in result.lower()


async def test_play_artist_success(play_module):
    sp = _mock_sp()
    # First call returns artist, second call returns tracks for that artist
    sp.search.side_effect = [
        _fake_artist_search(),
        {"tracks": {"items": [{"uri": f"spotify:track:{i}"} for i in range(5)]}},
    ]

    with patch("modules.spotify._get_client", return_value=sp):
        result = await play_module.run(query="Arctic Monkeys", type="artist")

    sp.start_playback.assert_called_once()
    assert "Arctic Monkeys" in result


async def test_play_album_success(play_module):
    sp = _mock_sp()
    sp.search.return_value = _fake_album_search()

    with patch("modules.spotify._get_client", return_value=sp):
        result = await play_module.run(query="AM", type="album")

    sp.start_playback.assert_called_once_with(device_id="test-device-id", context_uri="spotify:album:xyz")
    assert "AM" in result
    assert "Arctic Monkeys" in result


async def test_play_playlist_success(play_module):
    sp = _mock_sp()
    sp.current_user_playlists.return_value = {
        "items": [{
            "name": "Chill Vibes",
            "uri": "spotify:playlist:ppp",
            "owner": {"id": "user1", "display_name": "User"},
            "tracks": {"total": 10},
        }],
        "next": None,
    }

    with patch("modules.spotify._get_client", return_value=sp):
        result = await play_module.run(query="Chill Vibes", type="playlist")

    sp.start_playback.assert_called_once_with(device_id="test-device-id", context_uri="spotify:playlist:ppp")
    assert "Chill Vibes" in result


async def test_play_defaults_to_track_type(play_module):
    sp = _mock_sp()
    sp.search.side_effect = [
        _fake_track_search(),
        _fake_artist_track_fill(),
    ]

    with patch("modules.spotify._get_client", return_value=sp):
        await play_module.run(query="some song")

    first_call = sp.search.call_args_list[0]
    assert first_call.kwargs.get("type") == "track" or "track" in str(first_call)


async def test_play_no_results(play_module):
    sp = _mock_sp()
    sp.search.return_value = {"tracks": {"items": []}}

    with patch("modules.spotify._get_client", return_value=sp):
        result = await play_module.run(query="xyzunknownsong123")

    assert "No track found" in result or "No Spotify" in result


async def test_play_empty_query_returns_error(play_module):
    with patch("modules.spotify._get_client", return_value=_mock_sp()):
        result = await play_module.run(query="")

    assert "error" in result.lower() or "empty" in result.lower()


async def test_play_not_configured(play_module):
    with patch("modules.spotify._get_client", return_value=None):
        result = await play_module.run(query="test")

    assert "not configured" in result.lower() or "spotify_auth" in result.lower()


async def test_play_exception_returns_error_string(play_module):
    sp = _mock_sp()
    sp.search.side_effect = RuntimeError("network error")

    with patch("modules.spotify._get_client", return_value=sp):
        result = await play_module.run(query="test")

    assert "failed" in result.lower() or "error" in result.lower()


# ---------------------------------------------------------------------------
# SpotifyControlModule tests
# ---------------------------------------------------------------------------


async def test_control_pause(control_module):
    sp = _mock_sp()
    with patch("modules.spotify._get_client", return_value=sp):
        result = await control_module.run(action="pause")

    sp.pause_playback.assert_called_once()
    assert "paused" in result.lower()


async def test_control_resume(control_module):
    sp = _mock_sp()
    with patch("modules.spotify._get_client", return_value=sp):
        result = await control_module.run(action="resume")

    sp.start_playback.assert_called_once()
    assert "resumed" in result.lower()


async def test_control_next(control_module):
    sp = _mock_sp()
    with patch("modules.spotify._get_client", return_value=sp), \
         patch("modules.spotify._now_playing_text", return_value="Now playing: In the End by Linkin Park"):
        result = await control_module.run(action="next")

    sp.next_track.assert_called_once()
    assert "In the End" in result


async def test_control_previous(control_module):
    sp = _mock_sp()
    with patch("modules.spotify._get_client", return_value=sp), \
         patch("modules.spotify._now_playing_text", return_value="Now playing: Numb by Linkin Park"):
        result = await control_module.run(action="previous")

    sp.previous_track.assert_called_once()
    assert "Numb" in result


async def test_control_volume(control_module):
    sp = _mock_sp()
    with patch("modules.spotify._get_client", return_value=sp):
        result = await control_module.run(action="volume", volume=75)

    sp.volume.assert_called_once_with(75, device_id="test-device-id")
    assert "75" in result


async def test_control_volume_clamped(control_module):
    sp = _mock_sp()
    with patch("modules.spotify._get_client", return_value=sp):
        await control_module.run(action="volume", volume=999)

    sp.volume.assert_called_once_with(100, device_id="test-device-id")


async def test_control_unknown_action(control_module):
    sp = _mock_sp()
    with patch("modules.spotify._get_client", return_value=sp):
        result = await control_module.run(action="dance")

    assert "unknown" in result.lower() or "valid" in result.lower()


async def test_control_not_configured(control_module):
    with patch("modules.spotify._get_client", return_value=None):
        result = await control_module.run(action="pause")

    assert "not configured" in result.lower()


# ---------------------------------------------------------------------------
# SpotifyNowPlayingModule tests
# ---------------------------------------------------------------------------


async def test_now_playing_returns_track_info(now_playing_module):
    sp = _mock_sp()
    sp.current_playback.return_value = _fake_now_playing()

    with patch("modules.spotify._get_client", return_value=sp):
        result = await now_playing_module.run()

    assert "Bohemian Rhapsody" in result
    assert "Queen" in result
    assert "A Night at the Opera" in result
    assert "Playing" in result


async def test_now_playing_shows_paused_state(now_playing_module):
    sp = _mock_sp()
    sp.current_playback.return_value = _fake_now_playing(is_playing=False)

    with patch("modules.spotify._get_client", return_value=sp):
        result = await now_playing_module.run()

    assert "Paused" in result


async def test_now_playing_nothing_playing(now_playing_module):
    sp = _mock_sp()
    sp.current_playback.return_value = None

    with patch("modules.spotify._get_client", return_value=sp):
        result = await now_playing_module.run()

    assert "Nothing" in result or "nothing" in result


async def test_now_playing_not_configured(now_playing_module):
    with patch("modules.spotify._get_client", return_value=None):
        result = await now_playing_module.run()

    assert "not configured" in result.lower()


async def test_now_playing_exception_returns_error_string(now_playing_module):
    sp = _mock_sp()
    sp.current_playback.side_effect = RuntimeError("connection lost")

    with patch("modules.spotify._get_client", return_value=sp):
        result = await now_playing_module.run()

    assert "failed" in result.lower() or "error" in result.lower()


# ---------------------------------------------------------------------------
# SpotifyPlayModule — user playlist + liked songs tests
# ---------------------------------------------------------------------------


async def test_play_user_playlist_by_name(play_module):
    """Finds a user's own playlist by name instead of falling back to public search."""
    sp = _mock_sp()
    sp.current_user_playlists.return_value = _fake_user_playlists()

    with patch("modules.spotify._get_client", return_value=sp):
        result = await play_module.run(query="My Workout Mix", type="playlist")

    sp.start_playback.assert_called_once_with(
        device_id="test-device-id", context_uri="spotify:playlist:owned1"
    )
    assert "My Workout Mix" in result


async def test_play_user_playlist_with_filler_words(play_module):
    """'my Workout Mix playlist' still finds the 'My Workout Mix' playlist."""
    sp = _mock_sp()
    sp.current_user_playlists.return_value = _fake_user_playlists()

    with patch("modules.spotify._get_client", return_value=sp):
        result = await play_module.run(query="my Workout Mix playlist", type="playlist")

    sp.start_playback.assert_called_once_with(
        device_id="test-device-id", context_uri="spotify:playlist:owned1"
    )
    assert "My Workout Mix" in result


async def test_play_liked_songs_alias(play_module):
    """'liked songs' query plays from saved tracks, not a regular playlist."""
    sp = _mock_sp()
    sp.current_user_saved_tracks.return_value = _fake_saved_tracks(total=5)

    with patch("modules.spotify._get_client", return_value=sp):
        result = await play_module.run(query="liked songs", type="playlist")

    sp.start_playback.assert_called_once()
    assert "liked" in result.lower()


async def test_play_liked_songs_empty(play_module):
    sp = _mock_sp()
    sp.current_user_saved_tracks.return_value = {"total": 0, "items": []}

    with patch("modules.spotify._get_client", return_value=sp):
        result = await play_module.run(query="liked", type="playlist")

    assert "no liked" in result.lower() or "no saved" in result.lower()


# ---------------------------------------------------------------------------
# SpotifyMyPlaylistsModule tests
# ---------------------------------------------------------------------------


async def test_my_playlists_all(my_playlists_module):
    sp = _mock_sp()
    sp.current_user.return_value = {"id": "user123"}
    sp.current_user_playlists.return_value = _fake_user_playlists("user123")
    sp.current_user_saved_tracks.return_value = _fake_saved_tracks(total=42)

    with patch("modules.spotify._get_client", return_value=sp):
        result = await my_playlists_module.run()

    assert "My Workout Mix" in result
    assert "Indie Discovers" in result
    assert "42" in result  # Liked Songs count


async def test_my_playlists_mine_only(my_playlists_module):
    sp = _mock_sp()
    sp.current_user.return_value = {"id": "user123"}
    sp.current_user_playlists.return_value = _fake_user_playlists("user123")

    with patch("modules.spotify._get_client", return_value=sp):
        result = await my_playlists_module.run(filter="mine")

    assert "My Workout Mix" in result
    assert "Indie Discovers" not in result


async def test_my_playlists_saved_only(my_playlists_module):
    sp = _mock_sp()
    sp.current_user.return_value = {"id": "user123"}
    sp.current_user_playlists.return_value = _fake_user_playlists("user123")
    sp.current_user_saved_tracks.return_value = _fake_saved_tracks(total=10)

    with patch("modules.spotify._get_client", return_value=sp):
        result = await my_playlists_module.run(filter="saved")

    assert "Indie Discovers" in result
    assert "My Workout Mix" not in result


async def test_my_playlists_not_configured(my_playlists_module):
    with patch("modules.spotify._get_client", return_value=None):
        result = await my_playlists_module.run()

    assert "not configured" in result.lower()


# ---------------------------------------------------------------------------
# SpotifyControlModule — shuffle tests
# ---------------------------------------------------------------------------


async def test_shuffle_on(control_module):
    sp = _mock_sp()
    with patch("modules.spotify._get_client", return_value=sp):
        result = await control_module.run(action="shuffle", state="on")

    sp.shuffle.assert_called_once_with(True, device_id="test-device-id")
    assert "enabled" in result.lower()


async def test_shuffle_off(control_module):
    sp = _mock_sp()
    with patch("modules.spotify._get_client", return_value=sp):
        result = await control_module.run(action="shuffle", state="off")

    sp.shuffle.assert_called_once_with(False, device_id="test-device-id")
    assert "disabled" in result.lower()


async def test_shuffle_toggle_when_off(control_module):
    """Toggle turns shuffle ON when it is currently OFF."""
    sp = _mock_sp()
    sp.current_playback.return_value = {"shuffle_state": False, "is_playing": True}

    with patch("modules.spotify._get_client", return_value=sp):
        result = await control_module.run(action="shuffle", state="toggle")

    sp.shuffle.assert_called_once_with(True, device_id="test-device-id")
    assert "enabled" in result.lower()


async def test_shuffle_toggle_when_on(control_module):
    """Toggle turns shuffle OFF when it is currently ON."""
    sp = _mock_sp()
    sp.current_playback.return_value = {"shuffle_state": True, "is_playing": True}

    with patch("modules.spotify._get_client", return_value=sp):
        result = await control_module.run(action="shuffle")  # default state = toggle

    sp.shuffle.assert_called_once_with(False, device_id="test-device-id")
    assert "disabled" in result.lower()


async def test_shuffle_toggle_no_playback(control_module):
    """Toggle defaults to enabling shuffle when no playback state is available."""
    sp = _mock_sp()
    sp.current_playback.return_value = None

    with patch("modules.spotify._get_client", return_value=sp):
        result = await control_module.run(action="shuffle", state="toggle")

    sp.shuffle.assert_called_once_with(True, device_id="test-device-id")
    assert "enabled" in result.lower()


# ---------------------------------------------------------------------------
# SpotifyQueueModule tests
# ---------------------------------------------------------------------------


async def test_queue_track_success(queue_module):
    sp = _mock_sp()
    sp.search.return_value = _fake_track_search(name="Stairway to Heaven", artist="Led Zeppelin",
                                                uri="spotify:track:stairway")

    with patch("modules.spotify._get_client", return_value=sp):
        result = await queue_module.run(query="Stairway to Heaven")

    sp.add_to_queue.assert_called_once_with("spotify:track:stairway", device_id="test-device-id")
    assert "Stairway to Heaven" in result
    assert "Led Zeppelin" in result


async def test_queue_track_not_found(queue_module):
    sp = _mock_sp()
    sp.search.return_value = {"tracks": {"items": []}}

    with patch("modules.spotify._get_client", return_value=sp):
        result = await queue_module.run(query="xyzunknown999")

    sp.add_to_queue.assert_not_called()
    assert "no track found" in result.lower()


async def test_queue_empty_query(queue_module):
    with patch("modules.spotify._get_client", return_value=_mock_sp()):
        result = await queue_module.run(query="")

    assert "error" in result.lower() or "empty" in result.lower()


async def test_queue_not_configured(queue_module):
    with patch("modules.spotify._get_client", return_value=None):
        result = await queue_module.run(query="any song")

    assert "not configured" in result.lower()


async def test_queue_exception_returns_error_string(queue_module):
    sp = _mock_sp()
    sp.search.side_effect = RuntimeError("network error")

    with patch("modules.spotify._get_client", return_value=sp):
        result = await queue_module.run(query="some song")

    assert "failed" in result.lower() or "error" in result.lower()


async def test_queue_parses_by_format(queue_module):
    """'X by Y' queries are reformatted to track:X artist:Y before searching."""
    sp = _mock_sp()
    sp.search.return_value = _fake_track_search(
        name="Believer", artist="Imagine Dragons", uri="spotify:track:believer"
    )

    with patch("modules.spotify._get_client", return_value=sp):
        result = await queue_module.run(query="Believer by Imagine Dragons")

    call_args = sp.search.call_args
    q_used = call_args.kwargs.get("q") or call_args.args[0]
    assert "track:Believer" in q_used
    assert "artist:Imagine Dragons" in q_used
    assert "Believer" in result
    assert "Imagine Dragons" in result


# ---------------------------------------------------------------------------
# SpotifyPlayModule — _parse_track_query integration tests
# ---------------------------------------------------------------------------


async def test_play_track_parses_by_format(play_module):
    """'Title by Artist' queries are reformatted to track:Title artist:Artist before searching."""
    sp = _mock_sp()
    sp.search.side_effect = [
        _fake_track_search(name="I'm Happy", artist="The Goo Goo Dolls", uri="spotify:track:imhappy"),
        _fake_artist_track_fill(artist="The Goo Goo Dolls", playing_uri="spotify:track:imhappy"),
    ]

    with patch("modules.spotify._get_client", return_value=sp):
        result = await play_module.run(query="I'm Happy by The Goo Goo Dolls", type="track")

    # call_args_list[0] is the first (track) search; subsequent calls are the best-effort queue fill
    first_call = sp.search.call_args_list[0]
    q_used = first_call.kwargs.get("q") or first_call.args[0]
    assert "track:I'm Happy" in q_used
    assert "artist:The Goo Goo Dolls" in q_used
    assert "I'm Happy" in result
    assert "The Goo Goo Dolls" in result


async def test_play_track_parses_dash_format(play_module):
    """'Title - Artist' queries are also reformatted to field filter syntax."""
    sp = _mock_sp()
    sp.search.side_effect = [
        _fake_track_search(name="Stairway to Heaven", artist="Led Zeppelin", uri="spotify:track:stairway"),
        _fake_artist_track_fill(artist="Led Zeppelin", playing_uri="spotify:track:stairway"),
    ]

    with patch("modules.spotify._get_client", return_value=sp):
        result = await play_module.run(query="Stairway to Heaven - Led Zeppelin", type="track")

    first_call = sp.search.call_args_list[0]
    q_used = first_call.kwargs.get("q") or first_call.args[0]
    assert "track:Stairway to Heaven" in q_used
    assert "artist:Led Zeppelin" in q_used
    assert "Stairway to Heaven" in result


async def test_play_track_plain_query_unchanged(play_module):
    """A plain track name (no 'by' or '-') is passed to search without modification."""
    sp = _mock_sp()
    sp.search.side_effect = [
        _fake_track_search(name="Bohemian Rhapsody", artist="Queen"),
        _fake_artist_track_fill(artist="Queen"),
    ]

    with patch("modules.spotify._get_client", return_value=sp):
        await play_module.run(query="Bohemian Rhapsody", type="track")

    # First search call should receive the plain query with no field filter prefix
    first_call = sp.search.call_args_list[0]
    q_used = first_call.kwargs.get("q") or first_call.args[0]
    assert q_used == "Bohemian Rhapsody"
