"""CC Workflow — delete a workflow."""

import logging

from modules.base import NovaModule
from modules.cc_workflows._store import load_workflow, delete_workflow

logger = logging.getLogger(__name__)


class CCWorkflowDeleteModule(NovaModule):
    name: str = "cc_workflow_delete"
    description: str = "Delete a Claude Code workflow and its stored data."
    parameters: dict = {
        "type": "object",
        "properties": {
            "workflow_id": {
                "type": "string",
                "description": "The workflow ID to delete",
            },
        },
        "required": ["workflow_id"],
    }

    async def run(self, **kwargs) -> str:
        wf_id: str = kwargs.get("workflow_id", "").strip()

        if not wf_id:
            return "Error: workflow_id is required."

        try:
            # Load first to show confirmation details
            wf = await load_workflow(wf_id)
            if wf is None:
                return f"Error: workflow '{wf_id}' not found."

            title = wf.get("title", "untitled")
            deleted = await delete_workflow(wf_id)

            if deleted:
                return f"Workflow '{wf_id}' ({title}) deleted."
            else:
                return f"Error: workflow '{wf_id}' could not be deleted."
        except Exception as exc:
            logger.exception("cc_workflow_delete failed")
            return f"Error deleting workflow: {exc}"
