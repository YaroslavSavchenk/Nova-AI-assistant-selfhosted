"""Wikipedia lookup tool — summarizes topics via Wikipedia REST API."""

import logging
from urllib.parse import quote

import httpx

from modules.base import NovaModule

logger = logging.getLogger(__name__)

_HTTP_TIMEOUT = 10


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
