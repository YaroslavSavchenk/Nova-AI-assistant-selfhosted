"""Recall facts tool — lists stored long-term facts."""

import logging
from modules.base import NovaModule
from core.long_term_memory import LongTermMemory

logger = logging.getLogger(__name__)


class RecallFactsModule(NovaModule):
    name: str = "list_facts"
    description: str = (
        "List all long-term facts stored about the user. "
        "Use this when the user asks what you know about them, or to check before storing a duplicate fact. "
        "Optionally filter by category."
    )
    parameters: dict = {
        "type": "object",
        "properties": {
            "category": {
                "type": "string",
                "description": "Optional category filter (e.g. 'preference', 'personal', 'work')",
            },
        },
        "required": [],
    }

    def __init__(self, ltm: LongTermMemory) -> None:
        self._ltm = ltm

    async def run(self, **kwargs) -> str:
        try:
            category: str | None = kwargs.get("category", "").strip() or None
            facts = await self._ltm.list_facts(category=category)
            if not facts:
                label = f" in category '{category}'" if category else ""
                return f"No facts stored{label} yet."
            lines = [f"#{f['id']} [{f['category']}] {f['content']}" for f in facts]
            return "Stored facts:\n" + "\n".join(lines)
        except Exception as exc:
            logger.exception("list_facts failed")
            return f"Failed to retrieve facts: {exc}"
