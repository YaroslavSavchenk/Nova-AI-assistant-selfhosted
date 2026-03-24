"""PC control — read and write per-project development notes."""

import asyncio
import logging
import os
import re

from modules.base import NovaModule

logger = logging.getLogger(__name__)

_SAFE_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


def _sanitize_project_name(name: str) -> str | None:
    """Return the name if safe for use as a filename, else None."""
    if _SAFE_NAME_RE.match(name):
        return name
    return None


class ProjectNotesReadModule(NovaModule):
    name: str = "pc_read_notes"
    description: str = (
        "Read the development notes or checklist for a project. Use this to "
        "check what needs to be done, current status, or any saved context "
        "about a project."
    )
    parameters: dict = {
        "type": "object",
        "properties": {
            "project": {
                "type": "string",
                "description": "Project name from the registered projects list",
            },
        },
        "required": ["project"],
    }

    def __init__(self, projects: dict, notes_dir: str = "data/notes") -> None:
        self.projects = projects
        self.notes_dir = notes_dir

    async def run(self, **kwargs) -> str:
        project: str = kwargs.get("project", "")
        try:
            if not project:
                return "Error: project name is required."

            if project not in self.projects:
                available = ", ".join(self.projects.keys()) if self.projects else "none"
                return f"Error: unknown project '{project}'. Available projects: {available}"

            safe_name = _sanitize_project_name(project)
            if not safe_name:
                return f"Error: invalid project name '{project}'. Use only alphanumeric, hyphens, and underscores."

            notes_path = os.path.join(self.notes_dir, f"{safe_name}.md")

            if not os.path.isfile(notes_path):
                return f"No notes found for project '{project}'. Use pc_write_notes to create some."

            content = await asyncio.to_thread(self._read_file, notes_path)
            return f"Notes for '{project}':\n\n{content}"
        except Exception as exc:
            logger.exception("pc_read_notes failed")
            return f"Error reading notes: {exc}"

    @staticmethod
    def _read_file(path: str) -> str:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()


class ProjectNotesWriteModule(NovaModule):
    name: str = "pc_write_notes"
    description: str = (
        "Write or update the development notes or checklist for a project. "
        "Use this to save progress, plans, steps, or any context about "
        "ongoing work."
    )
    parameters: dict = {
        "type": "object",
        "properties": {
            "project": {
                "type": "string",
                "description": "Project name from the registered projects list",
            },
            "content": {
                "type": "string",
                "description": "The notes content (markdown supported)",
            },
            "mode": {
                "type": "string",
                "enum": ["replace", "append"],
                "description": "Write mode: 'replace' overwrites, 'append' adds to existing (default: replace)",
            },
        },
        "required": ["project", "content"],
    }

    def __init__(self, projects: dict, notes_dir: str = "data/notes") -> None:
        self.projects = projects
        self.notes_dir = notes_dir

    async def run(self, **kwargs) -> str:
        project: str = kwargs.get("project", "")
        content: str = kwargs.get("content", "")
        mode: str = kwargs.get("mode", "replace")

        try:
            if not project:
                return "Error: project name is required."

            if not content:
                return "Error: content cannot be empty."

            if mode not in ("replace", "append"):
                return f"Error: invalid mode '{mode}'. Use 'replace' or 'append'."

            if project not in self.projects:
                available = ", ".join(self.projects.keys()) if self.projects else "none"
                return f"Error: unknown project '{project}'. Available projects: {available}"

            safe_name = _sanitize_project_name(project)
            if not safe_name:
                return f"Error: invalid project name '{project}'. Use only alphanumeric, hyphens, and underscores."

            await asyncio.to_thread(self._write_file, safe_name, content, mode)

            if mode == "append":
                return f"Appended to notes for project '{project}'."
            return f"Wrote notes for project '{project}'."
        except Exception as exc:
            logger.exception("pc_write_notes failed")
            return f"Error writing notes: {exc}"

    def _write_file(self, safe_name: str, content: str, mode: str) -> None:
        os.makedirs(self.notes_dir, exist_ok=True)
        notes_path = os.path.join(self.notes_dir, f"{safe_name}.md")
        file_mode = "a" if mode == "append" else "w"
        with open(notes_path, file_mode, encoding="utf-8") as f:
            f.write(content)
