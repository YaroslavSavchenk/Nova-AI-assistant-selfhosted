"""
Tests for modules/web_search.py
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from modules.web_search import WebSearchModule


@pytest.fixture
def module():
    return WebSearchModule()


def _fake_results(n: int = 3) -> list[dict]:
    return [
        {
            "title": f"Result {i}",
            "href": f"https://example.com/{i}",
            "body": f"Snippet for result {i}.",
        }
        for i in range(1, n + 1)
    ]


# ---------------------------------------------------------------------------
# Helpers: patch DDGS as an async context manager
# ---------------------------------------------------------------------------


def _make_ddgs_patch(results):
    """Return a patch target and a mock that yields results from atext."""
    mock_ddgs_instance = AsyncMock()
    mock_ddgs_instance.atext = AsyncMock(return_value=results)

    # DDGS is used as `async with DDGS() as ddgs` so we need __aenter__
    mock_ddgs_cm = AsyncMock()
    mock_ddgs_cm.__aenter__ = AsyncMock(return_value=mock_ddgs_instance)
    mock_ddgs_cm.__aexit__ = AsyncMock(return_value=False)

    mock_ddgs_cls = MagicMock(return_value=mock_ddgs_cm)
    return mock_ddgs_cls, mock_ddgs_instance


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_results_formatted_correctly(module):
    """Results include title, URL, and snippet."""
    mock_ddgs_cls, mock_ddgs_instance = _make_ddgs_patch(_fake_results(2))

    with patch("modules.web_search.DDGS", mock_ddgs_cls):
        result = await module.run(query="test query")

    assert "test query" in result
    assert "Result 1" in result
    assert "https://example.com/1" in result
    assert "Snippet for result 1." in result
    assert "Result 2" in result
    assert "https://example.com/2" in result


@pytest.mark.asyncio
async def test_max_results_capped_at_10(module):
    """max_results above 10 is silently capped to 10."""
    mock_ddgs_cls, mock_ddgs_instance = _make_ddgs_patch(_fake_results(3))

    with patch("modules.web_search.DDGS", mock_ddgs_cls):
        await module.run(query="cap test", max_results=99)

    # The call to atext must have been made with max_results=10
    call_kwargs = mock_ddgs_instance.atext.call_args
    assert call_kwargs.kwargs.get("max_results") == 10 or call_kwargs.args[1] == 10


@pytest.mark.asyncio
async def test_max_results_default_is_5(module):
    """When max_results is omitted the default of 5 is used."""
    mock_ddgs_cls, mock_ddgs_instance = _make_ddgs_patch(_fake_results(3))

    with patch("modules.web_search.DDGS", mock_ddgs_cls):
        await module.run(query="default results")

    call_kwargs = mock_ddgs_instance.atext.call_args
    passed = call_kwargs.kwargs.get("max_results") or call_kwargs.args[1]
    assert passed == 5


@pytest.mark.asyncio
async def test_exception_returns_error_string_not_raise(module):
    """Any exception from DDGS is caught and returned as an error string."""
    mock_ddgs_cls = MagicMock(side_effect=RuntimeError("network failure"))

    with patch("modules.web_search.DDGS", mock_ddgs_cls):
        result = await module.run(query="broken query")

    assert "Web search failed" in result
    assert "network failure" in result


@pytest.mark.asyncio
async def test_no_results_returns_friendly_message(module):
    """Empty result list returns a user-friendly message."""
    mock_ddgs_cls, _ = _make_ddgs_patch([])

    with patch("modules.web_search.DDGS", mock_ddgs_cls):
        result = await module.run(query="very obscure query xyz")

    assert "No results found" in result


@pytest.mark.asyncio
async def test_empty_query_returns_error(module):
    """An empty query string returns an error without calling DDGS."""
    mock_ddgs_cls, _ = _make_ddgs_patch([])

    with patch("modules.web_search.DDGS", mock_ddgs_cls):
        result = await module.run(query="")

    assert "empty" in result.lower() or "error" in result.lower()
    mock_ddgs_cls.assert_not_called()
