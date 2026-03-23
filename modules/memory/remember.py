"""Remember fact tool — stores a long-term fact about the user."""

import logging
from modules.base import NovaModule
from core.long_term_memory import LongTermMemory

logger = logging.getLogger(__name__)


class RememberFactModule(NovaModule):
    name: str = "remember_fact"
    description: str = (
        "Store a long-term fact about the user that should persist across sessions. "
        "Use this when the user explicitly asks you to remember something, or when they share "
        "important personal preferences, names, context, or settings that would be useful to know in future conversations. "
        "Examples: 'Remember I prefer dark mode', 'My name is Sava', 'I work as a software developer'."
    )
    parameters: dict = {
        "type": "object",
        "properties": {
            "content": {
                "type": "string",
                "description": "The fact to remember, written as a clear statement",
            },
            "category": {
                "type": "string",
                "description": "Optional category (e.g. 'preference', 'personal', 'work'). Defaults to 'general'.",
            },
        },
        "required": ["content"],
    }

    def __init__(self, ltm: LongTermMemory) -> None:
        self._ltm = ltm

    async def run(self, **kwargs) -> str:
        try:
            content: str = kwargs.get("content", "").strip()
            if not content:
                return "Error: fact content cannot be empty."
            category: str = kwargs.get("category", "general").strip() or "general"
            fact_id = await self._ltm.add_fact(content, category)
            return f"Remembered (#{fact_id}): {content}"
        except Exception as exc:
            logger.exception("remember_fact failed")
            return f"Failed to store fact: {exc}"
