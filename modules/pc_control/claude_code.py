"""PC control — send a prompt to Claude Code CLI."""

import asyncio
import logging
import os

from modules.base import NovaModule

logger = logging.getLogger(__name__)

_MAX_OUTPUT = 6000


class ClaudeCodeModule(NovaModule):
    name: str = "pc_claude_code"
    description: str = (
        "Send a prompt to Claude Code CLI and return its response. "
        "Use for code explanation, analysis, or getting AI assistance on files."
    )
    parameters: dict = {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "The prompt to send to Claude Code",
            },
            "working_directory": {
                "type": "string",
                "description": "Working directory for Claude Code (defaults to home directory)",
            },
        },
        "required": ["prompt"],
    }

    def __init__(self, timeout: int = 120) -> None:
        self.timeout = timeout

    async def run(self, **kwargs) -> str:
        prompt: str = kwargs.get("prompt", "")
        working_directory: str = kwargs.get("working_directory", "")

        if not prompt.strip():
            return "Error: prompt cannot be empty."

        try:
            cwd = working_directory if working_directory else os.path.expanduser("~")

            proc = await asyncio.create_subprocess_exec(
                "claude", "-p", prompt,
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
