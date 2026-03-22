"""
Tests for modules/web_search.py
"""

import pytest
from unittest.mock import patch, MagicMock

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


def _patch_ddgs(results):
    """Patch DDGS so .text() returns the given results."""
    mock_instance = MagicMock()
    mock_instance.text = MagicMock(return_value=results)
    mock_cls = MagicMock(return_value=mock_instance)
    return mock_cls, mock_instance


async def test_results_formatted_correctly(module):
    mock_cls, _ = _patch_ddgs(_fake_results(2))
    with patch("modules.web_search.DDGS", mock_cls):
        result = await module.run(query="test query")

    assert "test query" in result
    assert "Result 1" in result
    assert "https://example.com/1" in result
    assert "Snippet for result 1." in result
    assert "Result 2" in result


async def test_max_results_capped_at_10(module):
    mock_cls, mock_instance = _patch_ddgs(_fake_results(3))
    with patch("modules.web_search.DDGS", mock_cls):
        await module.run(query="cap test", max_results=99)

    call_kwargs = mock_instance.text.call_args
    passed = call_kwargs.kwargs.get("max_results") or call_kwargs.args[1]
    assert passed == 10


async def test_max_results_default_is_5(module):
    mock_cls, mock_instance = _patch_ddgs(_fake_results(3))
    with patch("modules.web_search.DDGS", mock_cls):
        await module.run(query="default results")

    call_kwargs = mock_instance.text.call_args
    passed = call_kwargs.kwargs.get("max_results") or call_kwargs.args[1]
    assert passed == 5


async def test_exception_returns_error_string_not_raise(module):
    mock_cls = MagicMock(side_effect=RuntimeError("network failure"))
    with patch("modules.web_search.DDGS", mock_cls):
        result = await module.run(query="broken query")

    assert "Web search failed" in result
    assert "network failure" in result


async def test_no_results_returns_friendly_message(module):
    mock_cls, _ = _patch_ddgs([])
    with patch("modules.web_search.DDGS", mock_cls):
        result = await module.run(query="very obscure query xyz")

    assert "No results found" in result


async def test_empty_query_returns_error(module):
    mock_cls, _ = _patch_ddgs([])
    with patch("modules.web_search.DDGS", mock_cls):
        result = await module.run(query="")

    assert "empty" in result.lower() or "error" in result.lower()
    mock_cls.assert_not_called()
