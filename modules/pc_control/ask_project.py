"""PC control — ask a question about a project using notes + Claude Code."""

import asyncio
import logging
import os
import shutil

from modules.base import NovaModule
from modules.pc_control._safety import resolve_project

logger = logging.getLogger(__name__)

_MAX_OUTPUT = 6000


def _find_claude_cli() -> str | None:
    """Find the claude CLI binary, checking common locations."""
    found = shutil.which("claude")
    if found:
        return found
    for candidate in [
        os.path.expanduser("~/.local/bin/claude"),
        "/usr/local/bin/claude",
    ]:
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


class AskProjectModule(NovaModule):
    name: str = "pc_ask_project"
    description: str = (
        "Ask a question about a development project. Checks project notes "
        "first, then uses Claude Code to investigate the codebase and answer. "
        "Use this for ANY question about a project: status, phase, code, bugs, "
        "architecture, what to do next, etc."
    )
    parameters: dict = {
        "type": "object",
        "properties": {
            "project": {
                "type": "string",
                "description": "Project name (e.g. 'nova')",
            },
            "question": {
                "type": "string",
                "description": "The question to answer about the project",
            },
        },
        "required": ["project", "question"],
    }

    def __init__(
        self,
        projects: dict,
        notes_dir: str = "data/notes",
        timeout: int = 120,
    ) -> None:
        self.projects = projects
        self.notes_dir = notes_dir
        self.timeout = timeout

    async def run(self, **kwargs) -> str:
        project: str = kwargs.get("project", "")
        question: str = kwargs.get("question", "")

        if not project:
            return "Error: project name is required."
        if not question.strip():
            return "Error: question cannot be empty."

        try:
            resolved_key, project_info = resolve_project(project, self.projects)
            if not resolved_key or not project_info:
                available = ", ".join(self.projects.keys()) if self.projects else "none"
                return f"Error: unknown project '{project}'. Available projects: {available}"

            project_path = os.path.expanduser(project_info.get("path", ""))
            if not os.path.isdir(project_path):
                return f"Error: project path '{project_path}' does not exist."

            # Step 1: Check notes for saved context
            notes_context = self._read_notes(resolved_key)

            # Step 2: Build prompt with notes context and send to Claude Code
            claude_bin = _find_claude_cli()
            if not claude_bin:
                # Fall back to notes-only if Claude CLI is not available
                if notes_context:
                    return f"(Claude Code not available — answering from notes only)\n\n{notes_context}"
                return "Error: 'claude' CLI not found and no project notes exist."

            prompt = question
            if notes_context:
                prompt = (
                    f"Context from project notes:\n{notes_context}\n\n"
                    f"Question: {question}"
                )

            proc = await asyncio.create_subprocess_exec(
                claude_bin, "-p", prompt,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=project_path,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=self.timeout
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                return f"Claude Code timed out after {self.timeout}s."

            output = stdout.decode("utf-8", errors="replace").strip()
            err_output = stderr.decode("utf-8", errors="replace").strip()

            if proc.returncode != 0:
                return f"Claude Code error: {err_output or output or 'unknown error'}"

            if len(output) > _MAX_OUTPUT:
                output = output[:_MAX_OUTPUT] + "\n\n[truncated]"

            return output if output else "(Claude Code produced no output)"

        except Exception as exc:
            logger.exception("pc_ask_project failed")
            return f"Error: {exc}"

    def _read_notes(self, project_key: str) -> str:
        """Read notes file if it exists, return content or empty string."""
        notes_path = os.path.join(self.notes_dir, f"{project_key}.md")
        if not os.path.isfile(notes_path):
            return ""
        try:
            with open(notes_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            return ""
