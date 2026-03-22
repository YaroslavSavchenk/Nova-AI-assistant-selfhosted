"""
Web search module for Nova — uses DuckDuckGo via duckduckgo-search.
"""

import logging

from duckduckgo_search import DDGS
from modules.base import NovaModule

logger = logging.getLogger(__name__)


class WebSearchModule(NovaModule):
    """Search the web using DuckDuckGo."""

    name: str = "web_search"
    description: str = (
        "Search the web using DuckDuckGo. Use this when the user asks about current "
        "events, facts, or anything that requires up-to-date information."
    )
    parameters: dict = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query",
            },
            "max_results": {
                "type": "integer",
                "description": "Number of results to return (default 5, max 10)",
            },
        },
        "required": ["query"],
    }

    async def run(self, **kwargs) -> str:
        try:
            query: str = kwargs.get("query", "").strip()
            if not query:
                return "Error: search query cannot be empty."

            max_results: int = int(kwargs.get("max_results", 5))
            max_results = min(max(max_results, 1), 10)

            async with DDGS() as ddgs:
                results = await ddgs.atext(query, max_results=max_results)

            if not results:
                return f"No results found for: {query}"

            lines = [f"Search results for: {query}\n"]
            for i, r in enumerate(results, start=1):
                title = r.get("title", "No title")
                url = r.get("href", "No URL")
                snippet = r.get("body", "No snippet")
                lines.append(f"{i}. {title}\n   {url}\n   {snippet}\n")

            return "\n".join(lines).strip()

        except Exception as exc:
            logger.exception("WebSearchModule error")
            return f"Web search failed: {exc}"
