"""
Tests for modules/spotify/lyrics_search.py — SpotifyLyricsSearchModule.
"""

import pytest
import httpx
from unittest.mock import patch, MagicMock, AsyncMock

from modules.spotify import SpotifyLyricsSearchModule


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def module():
    return SpotifyLyricsSearchModule()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fake_genius_response(hits: list[dict]) -> dict:
    return {"response": {"hits": hits}}


def _fake_hit(title: str, artist: str) -> dict:
    return {
        "result": {
            "title": title,
            "primary_artist": {"name": artist},
        }
    }


def _mock_httpx_response(json_data: dict, status_code: int = 200):
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.json = MagicMock(return_value=json_data)
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


def _mock_httpx_client(response):
    """Return a mock async context manager yielding a client that returns response."""
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=response)
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    return mock_ctx


# ---------------------------------------------------------------------------
# Success cases
# ---------------------------------------------------------------------------


async def test_single_match_returns_confirmation_prompt(module):
    data = _fake_genius_response([_fake_hit("Bohemian Rhapsody", "Queen")])
    mock_ctx = _mock_httpx_client(_mock_httpx_response(data))

    with patch.dict("os.environ", {"GENIUS_ACCESS_TOKEN": "fake-token"}):
        with patch("modules.spotify.lyrics_search.httpx.AsyncClient", return_value=mock_ctx):
            result = await module.run(lyrics="is this the real life is this just fantasy")

    assert "Bohemian Rhapsody" in result
    assert "Queen" in result
    assert "yes" in result.lower() or "play" in result.lower()


async def test_multiple_matches_returns_numbered_list(module):
    data = _fake_genius_response([
        _fake_hit("Bohemian Rhapsody", "Queen"),
        _fake_hit("We Are the Champions", "Queen"),
        _fake_hit("Somebody to Love", "Queen"),
    ])
    mock_ctx = _mock_httpx_client(_mock_httpx_response(data))

    with patch.dict("os.environ", {"GENIUS_ACCESS_TOKEN": "fake-token"}):
        with patch("modules.spotify.lyrics_search.httpx.AsyncClient", return_value=mock_ctx):
            result = await module.run(lyrics="we will we will rock you")

    assert "1." in result
    assert "2." in result
    assert "3." in result
    assert "Bohemian Rhapsody" in result
    assert "We Are the Champions" in result
    assert "Somebody to Love" in result


async def test_max_three_candidates_returned(module):
    """Even if Genius returns more hits, we cap at 3."""
    data = _fake_genius_response([
        _fake_hit(f"Song {i}", "Artist") for i in range(10)
    ])
    mock_ctx = _mock_httpx_client(_mock_httpx_response(data))

    with patch.dict("os.environ", {"GENIUS_ACCESS_TOKEN": "fake-token"}):
        with patch("modules.spotify.lyrics_search.httpx.AsyncClient", return_value=mock_ctx):
            result = await module.run(lyrics="some lyric")

    assert "4." not in result


async def test_genius_query_uses_lyrics_as_search_term(module):
    """Verifies the lyrics snippet is passed as the search query."""
    data = _fake_genius_response([_fake_hit("Test Song", "Test Artist")])
    mock_resp = _mock_httpx_response(data)
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    with patch.dict("os.environ", {"GENIUS_ACCESS_TOKEN": "fake-token"}):
        with patch("modules.spotify.lyrics_search.httpx.AsyncClient", return_value=mock_ctx):
            await module.run(lyrics="stairway to heaven")

    call_kwargs = mock_client.get.call_args
    params = call_kwargs.kwargs.get("params", {})
    assert params.get("q") == "stairway to heaven"


# ---------------------------------------------------------------------------
# No results
# ---------------------------------------------------------------------------


async def test_no_results_returns_friendly_message(module):
    data = _fake_genius_response([])
    mock_ctx = _mock_httpx_client(_mock_httpx_response(data))

    with patch.dict("os.environ", {"GENIUS_ACCESS_TOKEN": "fake-token"}):
        with patch("modules.spotify.lyrics_search.httpx.AsyncClient", return_value=mock_ctx):
            result = await module.run(lyrics="xyznonexistentlyric999abc")

    assert "no songs found" in result.lower()
    assert "xyznonexistentlyric999abc" in result


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


async def test_empty_lyrics_returns_error(module):
    result = await module.run(lyrics="")
    assert "error" in result.lower() or "empty" in result.lower()


async def test_missing_token_returns_error(module):
    with patch.dict("os.environ", {}, clear=True):
        import os
        os.environ.pop("GENIUS_ACCESS_TOKEN", None)
        result = await module.run(lyrics="some lyric")

    assert "not configured" in result.lower() or "genius" in result.lower()


# ---------------------------------------------------------------------------
# API error handling
# ---------------------------------------------------------------------------


async def test_401_unauthorized_gives_clear_message(module):
    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        "401 Unauthorized", request=MagicMock(), response=mock_resp
    )
    mock_ctx = _mock_httpx_client(mock_resp)

    with patch.dict("os.environ", {"GENIUS_ACCESS_TOKEN": "bad-token"}):
        with patch("modules.spotify.lyrics_search.httpx.AsyncClient", return_value=mock_ctx):
            result = await module.run(lyrics="some lyric")

    assert "invalid" in result.lower() or "token" in result.lower()


async def test_network_error_returns_error_string(module):
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=httpx.RequestError("connection refused"))
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    with patch.dict("os.environ", {"GENIUS_ACCESS_TOKEN": "fake-token"}):
        with patch("modules.spotify.lyrics_search.httpx.AsyncClient", return_value=mock_ctx):
            result = await module.run(lyrics="some lyric")

    assert "network" in result.lower() or "error" in result.lower()


async def test_unexpected_exception_returns_error_string(module):
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=RuntimeError("something broke"))
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    with patch.dict("os.environ", {"GENIUS_ACCESS_TOKEN": "fake-token"}):
        with patch("modules.spotify.lyrics_search.httpx.AsyncClient", return_value=mock_ctx):
            result = await module.run(lyrics="some lyric")

    assert "failed" in result.lower() or "error" in result.lower()
