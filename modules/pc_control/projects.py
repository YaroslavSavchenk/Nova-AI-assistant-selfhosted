"""PC control — list registered development projects."""

import logging
import os

from modules.base import NovaModule

logger = logging.getLogger(__name__)


class ListProjectsModule(NovaModule):
    name: str = "pc_list_projects"
    description: str = (
        "List all registered development projects. Use this to find project "
        "names and paths before opening Claude Code or working with project files."
    )
    parameters: dict = {
        "type": "object",
        "properties": {},
    }

    def __init__(self, projects: dict) -> None:
        self.projects = projects

    async def run(self, **kwargs) -> str:
        try:
            if not self.projects:
                return "No projects registered. Add projects to the 'projects' section of config.yaml."

            lines = ["Registered projects:\n"]
            for key, info in self.projects.items():
                path = os.path.expanduser(info.get("path", ""))
                desc = info.get("description", "No description")
                lines.append(f"  - {key}: {path}")
                lines.append(f"    {desc}")
            return "\n".join(lines)
        except Exception as exc:
            logger.exception("pc_list_projects failed")
            return f"Error listing projects: {exc}"
