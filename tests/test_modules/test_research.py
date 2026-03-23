"""
Tests for the research package — NewsModule, WikipediaModule, SummarizeUrlModule.
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from modules.research import NewsModule, WikipediaModule, SummarizeUrlModule


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def news_module():
    return NewsModule()


@pytest.fixture
def wiki_module():
    return WikipediaModule()


@pytest.fixture
def url_module():
    return SummarizeUrlModule()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fake_feed(n: int = 3):
    """Build a fake feedparser result with n entries."""
    feed = MagicMock()
    feed.entries = [
        {
            "title": f"Headline {i} - Fake News",
            "source": {"title": f"Source {i}"},
            "published": "Sun, 01 Jan 2026 00:00:00 +0000",
            "link": f"https://news.example.com/article/{i}",
        }
        for i in range(1, n + 1)
    ]
    return feed


def _mock_httpx_response(status_code: int = 200, json_data: dict = None, text: str = "", content_type: str = "text/html"):
    """Build a mock httpx response."""
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.text = text
    mock_resp.headers = {"content-type": content_type}
    if json_data is not None:
        mock_resp.json = MagicMock(return_value=json_data)
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


def _mock_httpx_client(response):
    """Return a mock async context manager that yields a client returning response."""
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=response)
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    return mock_ctx


# ---------------------------------------------------------------------------
# NewsModule tests
# ---------------------------------------------------------------------------


async def test_news_returns_headlines(news_module):
    fake_feed = _fake_feed(3)
    with patch("modules.research.news.feedparser.parse", return_value=fake_feed):
        result = await news_module.run(topic="Python")

    assert "Python" in result
    assert "Headline 1" in result
    assert "Source 1" in result
    assert "https://news.example.com/article/1" in result


async def test_news_strips_source_from_title(news_module):
    """Google News titles often end with ' - Source Name' — should be stripped."""
    feed = MagicMock()
    feed.entries = [
        {
            "title": "Big Story Today - Reuters",
            "source": {"title": "Reuters"},
            "published": "",
            "link": "https://example.com",
        }
    ]
    with patch("modules.research.news.feedparser.parse", return_value=feed):
        result = await news_module.run(topic="test")

    assert "Big Story Today" in result
    assert result.count("Reuters") <= 2


async def test_news_max_articles_capped_at_10(news_module):
    fake_feed = _fake_feed(15)
    with patch("modules.research.news.feedparser.parse", return_value=fake_feed):
        result = await news_module.run(topic="AI", max_articles=99)

    assert result.count("https://news.example.com/article/") == 10


async def test_news_empty_topic_returns_error(news_module):
    result = await news_module.run(topic="")
    assert "error" in result.lower() or "empty" in result.lower()


async def test_news_no_entries_returns_friendly_message(news_module):
    empty_feed = MagicMock()
    empty_feed.entries = []
    with patch("modules.research.news.feedparser.parse", return_value=empty_feed):
        result = await news_module.run(topic="obscuretopicxyz")

    assert "No recent news found" in result


async def test_news_exception_returns_error_string(news_module):
    with patch("modules.research.news.feedparser.parse", side_effect=RuntimeError("timeout")):
        result = await news_module.run(topic="AI")

    assert "Failed to fetch news" in result
    assert "timeout" in result


# ---------------------------------------------------------------------------
# WikipediaModule tests
# ---------------------------------------------------------------------------


async def test_wiki_returns_summary(wiki_module):
    fake_data = {
        "title": "Python (programming language)",
        "extract": "Python is a high-level programming language.",
        "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Python_(programming_language)"}},
    }
    mock_ctx = _mock_httpx_client(_mock_httpx_response(200, json_data=fake_data))

    with patch("modules.research.wikipedia.httpx.AsyncClient", return_value=mock_ctx):
        result = await wiki_module.run(query="Python programming language")

    assert "Python (programming language)" in result
    assert "high-level programming language" in result
    assert "en.wikipedia.org" in result


async def test_wiki_404_returns_not_found(wiki_module):
    mock_resp = _mock_httpx_response(status_code=404)
    mock_ctx = _mock_httpx_client(mock_resp)

    with patch("modules.research.wikipedia.httpx.AsyncClient", return_value=mock_ctx):
        result = await wiki_module.run(query="ThisTopicDoesNotExistXYZ")

    assert "No Wikipedia article found" in result


async def test_wiki_empty_query_returns_error(wiki_module):
    result = await wiki_module.run(query="")
    assert "error" in result.lower() or "empty" in result.lower()


async def test_wiki_exception_returns_error_string(wiki_module):
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(side_effect=RuntimeError("network down"))
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    with patch("modules.research.wikipedia.httpx.AsyncClient", return_value=mock_ctx):
        result = await wiki_module.run(query="Python")

    assert "Wikipedia lookup failed" in result


# ---------------------------------------------------------------------------
# SummarizeUrlModule tests
# ---------------------------------------------------------------------------

_SAMPLE_HTML = """
<html>
<head><title>Test Page</title></head>
<body>
  <nav>Skip nav</nav>
  <article>
    <h1>Article Title</h1>
    <p>This is the main content of the article.</p>
    <p>Second paragraph with more details.</p>
  </article>
  <footer>Footer text</footer>
</body>
</html>
"""


async def test_summarize_url_extracts_article_content(url_module):
    mock_resp = _mock_httpx_response(200, text=_SAMPLE_HTML, content_type="text/html; charset=utf-8")
    mock_ctx = _mock_httpx_client(mock_resp)

    with patch("modules.research.summarize.httpx.AsyncClient", return_value=mock_ctx):
        result = await url_module.run(url="https://example.com/article")

    assert "Article Title" in result
    assert "main content of the article" in result
    assert "Skip nav" not in result
    assert "Footer text" not in result


async def test_summarize_url_truncates_long_content(url_module):
    long_html = f"<html><body><article><p>{'x' * 10000}</p></article></body></html>"
    mock_resp = _mock_httpx_response(200, text=long_html, content_type="text/html")
    mock_ctx = _mock_httpx_client(mock_resp)

    with patch("modules.research.summarize.httpx.AsyncClient", return_value=mock_ctx):
        result = await url_module.run(url="https://example.com/long")

    assert "truncated" in result
    assert len(result) < 6000


async def test_summarize_url_rejects_non_http(url_module):
    result = await url_module.run(url="ftp://example.com/file")
    assert "http" in result.lower() or "error" in result.lower()


async def test_summarize_url_empty_url_returns_error(url_module):
    result = await url_module.run(url="")
    assert "error" in result.lower() or "empty" in result.lower()


async def test_summarize_url_non_html_content_type(url_module):
    mock_resp = _mock_httpx_response(200, text="raw text", content_type="application/pdf")
    mock_ctx = _mock_httpx_client(mock_resp)

    with patch("modules.research.summarize.httpx.AsyncClient", return_value=mock_ctx):
        result = await url_module.run(url="https://example.com/file.pdf")

    assert "non-HTML" in result or "Cannot" in result


async def test_summarize_url_http_error_returns_error_string(url_module):
    import httpx
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(
        side_effect=httpx.RequestError("connection refused", request=MagicMock())
    )
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    with patch("modules.research.summarize.httpx.AsyncClient", return_value=mock_ctx):
        result = await url_module.run(url="https://down.example.com")

    assert "Network error" in result or "Failed" in result
