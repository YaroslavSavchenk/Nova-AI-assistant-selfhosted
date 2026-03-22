"""
Research module for Nova — news headlines, Wikipedia lookups, and URL summarization.

Three tools:
  - news_headlines: Fetch recent news via Google News RSS (no API key needed)
  - wikipedia_lookup: Summarize a topic using the Wikipedia REST API
  - summarize_url: Fetch and extract readable text from a URL
"""

import asyncio
import html
import logging
import re
from urllib.parse import quote

import feedparser
import httpx
from bs4 import BeautifulSoup

from modules.base import NovaModule

logger = logging.getLogger(__name__)

_HTTP_TIMEOUT = 10  # seconds


class NewsModule(NovaModule):
    """Fetch recent news headlines for a topic via Google News RSS."""

    name: str = "news_headlines"
    description: str = (
        "Fetch recent news headlines and summaries for a given topic or keyword. "
        "Use this when the user asks about current news, recent events, or what's happening with a specific subject."
    )
    parameters: dict = {
        "type": "object",
        "properties": {
            "topic": {
                "type": "string",
                "description": "The news topic or keyword to search for (e.g. 'AI', 'climate change', 'Formula 1')",
            },
            "max_articles": {
                "type": "integer",
                "description": "Number of articles to return (default 5, max 10)",
            },
        },
        "required": ["topic"],
    }

    async def run(self, **kwargs) -> str:
        try:
            topic: str = kwargs.get("topic", "").strip()
            if not topic:
                return "Error: news topic cannot be empty."

            max_articles: int = min(int(kwargs.get("max_articles", 5)), 10)
            max_articles = max(max_articles, 1)

            url = f"https://news.google.com/rss/search?q={quote(topic)}&hl=en-US&gl=US&ceid=US:en"

            loop = asyncio.get_event_loop()
            feed = await loop.run_in_executor(None, lambda: feedparser.parse(url))

            entries = feed.entries[:max_articles]
            if not entries:
                return f"No recent news found for: {topic}"

            lines = [f"Recent news for '{topic}':\n"]
            for i, entry in enumerate(entries, start=1):
                title = html.unescape(entry.get("title", "No title"))
                source = entry.get("source", {}).get("title", "Unknown source")
                published = entry.get("published", "")
                link = entry.get("link", "")
                # Google News titles often end with " - Source Name" — strip it
                if " - " in title:
                    title = title.rsplit(" - ", 1)[0]
                lines.append(f"{i}. {title.strip()}")
                lines.append(f"   Source: {source} | {published}")
                lines.append(f"   {link}\n")

            return "\n".join(lines).strip()

        except Exception as exc:
            logger.exception("NewsModule error")
            return f"Failed to fetch news: {exc}"


class WikipediaModule(NovaModule):
    """Look up a topic on Wikipedia and return a summary."""

    name: str = "wikipedia_lookup"
    description: str = (
        "Look up a topic, person, concept, or place on Wikipedia and return a summary. "
        "Use this for factual questions like 'who is X', 'what is Y', or 'explain Z'."
    )
    parameters: dict = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The topic or entity to look up (e.g. 'Python programming language', 'Elon Musk')",
            },
        },
        "required": ["query"],
    }

    _API_BASE = "https://en.wikipedia.org/api/rest_v1/page/summary"

    async def run(self, **kwargs) -> str:
        try:
            query: str = kwargs.get("query", "").strip()
            if not query:
                return "Error: query cannot be empty."

            title = query.replace(" ", "_")
            url = f"{self._API_BASE}/{quote(title)}"

            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT, follow_redirects=True) as client:
                response = await client.get(
                    url, headers={"User-Agent": "Nova-AI-Assistant/1.0"}
                )

            if response.status_code == 404:
                return f"No Wikipedia article found for: {query}"

            response.raise_for_status()
            data = response.json()

            title_out = data.get("title", query)
            extract = data.get("extract", "No summary available.")
            page_url = data.get("content_urls", {}).get("desktop", {}).get("page", "")

            result = f"Wikipedia — {title_out}\n\n{extract}"
            if page_url:
                result += f"\n\nFull article: {page_url}"
            return result

        except httpx.HTTPStatusError as exc:
            return f"Wikipedia lookup failed (HTTP {exc.response.status_code}): {exc}"
        except Exception as exc:
            logger.exception("WikipediaModule error")
            return f"Wikipedia lookup failed: {exc}"


class SummarizeUrlModule(NovaModule):
    """Fetch a webpage and return its readable text content for the LLM to summarize."""

    name: str = "summarize_url"
    description: str = (
        "Fetch a webpage and extract its main readable text content so you can read and summarize it. "
        "Use this when the user shares a URL and wants to know what's on the page."
    )
    parameters: dict = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The full URL of the webpage to fetch and summarize",
            },
        },
        "required": ["url"],
    }

    _MAX_CHARS = 4000

    async def run(self, **kwargs) -> str:
        try:
            url: str = kwargs.get("url", "").strip()
            if not url:
                return "Error: URL cannot be empty."
            if not url.startswith(("http://", "https://")):
                return "Error: URL must start with http:// or https://"

            async with httpx.AsyncClient(
                timeout=_HTTP_TIMEOUT,
                follow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0 (compatible; Nova-AI-Assistant/1.0)"},
            ) as client:
                response = await client.get(url)

            response.raise_for_status()
            content_type = response.headers.get("content-type", "")
            if "html" not in content_type:
                return f"URL returned non-HTML content ({content_type}). Cannot extract text."

            soup = BeautifulSoup(response.text, "html.parser")

            for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
                tag.decompose()

            main = soup.find("article") or soup.find("main") or soup.find("body")
            if not main:
                return "Could not extract readable content from this page."

            text = main.get_text(separator="\n", strip=True)
            text = re.sub(r"\n{3,}", "\n\n", text)

            if len(text) > self._MAX_CHARS:
                text = text[: self._MAX_CHARS] + "\n\n[content truncated — article continues]"

            return f"Content from {url}:\n\n{text}"

        except httpx.HTTPStatusError as exc:
            return f"Failed to fetch URL (HTTP {exc.response.status_code}): {url}"
        except httpx.RequestError as exc:
            return f"Network error fetching URL: {exc}"
        except Exception as exc:
            logger.exception("SummarizeUrlModule error")
            return f"Failed to summarize URL: {exc}"
