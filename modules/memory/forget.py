"""Forget fact tool — deletes a stored long-term fact."""

import logging
from modules.base import NovaModule
from core.long_term_memory import LongTermMemory

logger = logging.getLogger(__name__)


class ForgetFactModule(NovaModule):
    name: str = "forget_fact"
    description: str = (
        "Delete a stored long-term fact by its ID. "
        "Use list_facts first to find the ID. "
        "Use this when the user asks you to forget something or when a fact is outdated."
    )
    parameters: dict = {
        "type": "object",
        "properties": {
            "fact_id": {
                "type": "integer",
                "description": "The ID of the fact to delete (from list_facts)",
            },
        },
        "required": ["fact_id"],
    }

    def __init__(self, ltm: LongTermMemory) -> None:
        self._ltm = ltm

    async def run(self, **kwargs) -> str:
        try:
            fact_id = int(kwargs["fact_id"])
            deleted = await self._ltm.delete_fact(fact_id)
            if deleted:
                return f"Forgotten fact #{fact_id}."
            return f"No fact found with ID #{fact_id}."
        except KeyError:
            return "Error: fact_id is required. Use list_facts to find the ID."
        except Exception as exc:
            logger.exception("forget_fact failed")
            return f"Failed to delete fact: {exc}"
