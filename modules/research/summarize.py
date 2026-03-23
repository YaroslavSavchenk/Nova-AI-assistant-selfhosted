"""URL summarizer tool — fetches and extracts readable text from a webpage."""

import logging
import re

import httpx
from bs4 import BeautifulSoup

from modules.base import NovaModule

logger = logging.getLogger(__name__)

_HTTP_TIMEOUT = 10


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
