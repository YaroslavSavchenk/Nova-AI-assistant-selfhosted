"""PC control — send a prompt to Claude Code CLI."""

import asyncio
import logging
import os
import shutil

from modules.base import NovaModule

logger = logging.getLogger(__name__)

_MAX_OUTPUT = 6000


def _find_claude_cli() -> str | None:
    """Find the claude CLI binary, checking common locations."""
    # shutil.which checks PATH
    found = shutil.which("claude")
    if found:
        return found
    # Common install locations not always on PATH
    for candidate in [
        os.path.expanduser("~/.local/bin/claude"),
        "/usr/local/bin/claude",
    ]:
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


class ClaudeCodeModule(NovaModule):
    name: str = "pc_claude_code"
    description: str = (
        "Send a prompt to Claude Code CLI and return its response. "
        "Can target a specific project by name — use pc_list_projects to "
        "see available projects."
    )
    parameters: dict = {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "The prompt to send to Claude Code",
            },
            "project": {
                "type": "string",
                "description": (
                    "Project name from the registered projects list "
                    "(use pc_list_projects to see available projects)"
                ),
            },
            "working_directory": {
                "type": "string",
                "description": "Working directory for Claude Code (defaults to home directory)",
            },
        },
        "required": ["prompt"],
    }

    def __init__(self, timeout: int = 120, projects: dict | None = None) -> None:
        self.timeout = timeout
        self.projects = projects or {}

    async def run(self, **kwargs) -> str:
        prompt: str = kwargs.get("prompt", "")
        project: str = kwargs.get("project", "")
        working_directory: str = kwargs.get("working_directory", "")

        if not prompt.strip():
            return "Error: prompt cannot be empty."

        try:
            claude_bin = _find_claude_cli()
            if not claude_bin:
                return "Error: 'claude' CLI not found. Is Claude Code installed and on PATH?"

            # Project takes precedence over working_directory
            if project:
                project_info = self.projects.get(project)
                if not project_info:
                    available = ", ".join(self.projects.keys()) if self.projects else "none"
                    return f"Error: unknown project '{project}'. Available projects: {available}"
                cwd = os.path.expanduser(project_info.get("path", ""))
            elif working_directory:
                cwd = os.path.expanduser(working_directory)
            else:
                cwd = os.path.expanduser("~")

            if not os.path.isdir(cwd):
                return f"Error: working directory '{cwd}' does not exist."

            proc = await asyncio.create_subprocess_exec(
                claude_bin, "-p", prompt,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
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
                output = output[:_MAX_OUTPUT] + "\n\n[truncated — output exceeded 6000 chars]"

            return output if output else "(Claude Code produced no output)"

        except FileNotFoundError:
            return "Error: 'claude' CLI not found. Is Claude Code installed and on PATH?"
        except Exception as exc:
            logger.exception("pc_claude_code failed")
            return f"Error running Claude Code: {exc}"
