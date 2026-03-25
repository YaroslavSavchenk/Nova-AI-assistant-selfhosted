"""CC Workflow — create a new workflow."""

import logging
import os

from modules.base import NovaModule
from modules.cc_workflows._store import create_workflow, save_workflow
from modules.pc_control._safety import resolve_project

logger = logging.getLogger(__name__)


class CCWorkflowCreateModule(NovaModule):
    name: str = "cc_workflow_create"
    description: str = (
        "Create a new Claude Code workflow — a multi-step checklist of prompts "
        "that will be executed sequentially in a project directory with session "
        "continuity."
    )
    parameters: dict = {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "Short title describing what this workflow accomplishes",
            },
            "project": {
                "type": "string",
                "description": "Project name from the registered projects list",
            },
        },
        "required": ["title", "project"],
    }

    def __init__(self, projects: dict | None = None) -> None:
        self.projects = projects or {}

    async def run(self, **kwargs) -> str:
        title: str = kwargs.get("title", "").strip()
        project: str = kwargs.get("project", "").strip()

        if not title:
            return "Error: title cannot be empty."
        if not project:
            return "Error: project cannot be empty."

        try:
            resolved_key, project_info = resolve_project(project, self.projects)
            if not project_info:
                available = ", ".join(self.projects.keys()) if self.projects else "none"
                return f"Error: unknown project '{project}'. Available: {available}"

            project_path = os.path.expanduser(project_info.get("path", ""))
            if not os.path.isdir(project_path):
                return f"Error: project path '{project_path}' does not exist."

            wf = create_workflow(title=title, project=resolved_key, project_path=project_path)
            await save_workflow(wf)

            return (
                f"Workflow created.\n"
                f"  ID: {wf['id']}\n"
                f"  Title: {title}\n"
                f"  Project: {resolved_key}\n"
                f"  Path: {project_path}\n\n"
                f"Add steps with cc_workflow_add_step using workflow_id '{wf['id']}'."
            )
        except Exception as exc:
            logger.exception("cc_workflow_create failed")
            return f"Error creating workflow: {exc}"
