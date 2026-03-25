"""CC Workflow — view a workflow's details."""

import logging

from modules.base import NovaModule
from modules.cc_workflows._store import load_workflow

logger = logging.getLogger(__name__)

_OUTPUT_PREVIEW = 200


class CCWorkflowViewModule(NovaModule):
    name: str = "cc_workflow_view"
    description: str = (
        "View detailed information about a workflow including all steps, "
        "their status, and truncated output."
    )
    parameters: dict = {
        "type": "object",
        "properties": {
            "workflow_id": {
                "type": "string",
                "description": "The workflow ID to view",
            },
        },
        "required": ["workflow_id"],
    }

    async def run(self, **kwargs) -> str:
        wf_id: str = kwargs.get("workflow_id", "").strip()

        if not wf_id:
            return "Error: workflow_id is required."

        try:
            wf = await load_workflow(wf_id)
            if wf is None:
                return f"Error: workflow '{wf_id}' not found."

            steps = wf.get("steps", [])
            done = sum(1 for s in steps if s["status"] == "done")
            total = len(steps)

            lines = [
                f"Workflow: {wf['title']}",
                f"  ID: {wf['id']}",
                f"  Project: {wf['project']} ({wf.get('project_path', '')})",
                f"  Progress: {done}/{total} steps done",
                f"  Session: {wf.get('claude_session_id') or 'not started'}",
                f"  Created: {wf.get('created_at', 'unknown')}",
                f"  Updated: {wf.get('updated_at', 'unknown')}",
                "",
                "Steps:",
            ]

            status_icons = {
                "pending": "[ ]",
                "running": "[~]",
                "done": "[x]",
                "failed": "[!]",
            }

            for step in steps:
                icon = status_icons.get(step["status"], "[?]")
                lines.append(f"  {icon} Step {step['index']}: {step['prompt'][:120]}")

                if step.get("output"):
                    preview = step["output"][:_OUTPUT_PREVIEW]
                    if len(step["output"]) > _OUTPUT_PREVIEW:
                        preview += "..."
                    lines.append(f"      Output: {preview}")

                if step.get("started_at"):
                    lines.append(f"      Started: {step['started_at']}")
                if step.get("completed_at"):
                    lines.append(f"      Completed: {step['completed_at']}")

            return "\n".join(lines)
        except Exception as exc:
            logger.exception("cc_workflow_view failed")
            return f"Error viewing workflow: {exc}"
