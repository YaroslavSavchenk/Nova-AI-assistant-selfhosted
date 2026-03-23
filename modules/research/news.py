"""News headlines tool — fetches recent news via Google News RSS."""

import asyncio
import html
import logging
from urllib.parse import quote

import feedparser

from modules.base import NovaModule

logger = logging.getLogger(__name__)


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
