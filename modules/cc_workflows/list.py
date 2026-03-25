"""CC Workflow — list all workflows."""

import logging

from modules.base import NovaModule
from modules.cc_workflows._store import list_workflows

logger = logging.getLogger(__name__)


class CCWorkflowListModule(NovaModule):
    name: str = "cc_workflow_list"
    description: str = (
        "List all Claude Code workflows, optionally filtered by project."
    )
    parameters: dict = {
        "type": "object",
        "properties": {
            "project": {
                "type": "string",
                "description": "Filter by project name (optional)",
            },
        },
    }

    async def run(self, **kwargs) -> str:
        project: str = kwargs.get("project", "").strip() or None

        try:
            workflows = await list_workflows(project=project)

            if not workflows:
                msg = "No workflows found"
                if project:
                    msg += f" for project '{project}'"
                return msg + "."

            lines = [f"Found {len(workflows)} workflow(s):\n"]
            for wf in workflows:
                steps = wf.get("steps", [])
                done = sum(1 for s in steps if s["status"] == "done")
                failed = sum(1 for s in steps if s["status"] == "failed")
                total = len(steps)

                status_parts = [f"{done}/{total} done"]
                if failed:
                    status_parts.append(f"{failed} failed")
                progress = ", ".join(status_parts)

                lines.append(
                    f"  [{wf['id']}] {wf['title']}\n"
                    f"    Project: {wf['project']} | Steps: {progress}\n"
                    f"    Created: {wf.get('created_at', 'unknown')}"
                )

            return "\n".join(lines)
        except Exception as exc:
            logger.exception("cc_workflow_list failed")
            return f"Error listing workflows: {exc}"
