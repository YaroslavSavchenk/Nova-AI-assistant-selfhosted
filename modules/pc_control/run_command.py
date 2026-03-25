"""PC control — run a shell command from the allowed commands list."""

import asyncio
import logging
import shlex

from modules.base import NovaModule
from modules.pc_control._safety import validate_command

logger = logging.getLogger(__name__)

_MAX_OUTPUT = 4000


class RunCommandModule(NovaModule):
    name: str = "pc_run_command"
    description: str = (
        "Run a shell command from the allowed commands list. "
        "Use for listing files, checking processes, disk usage, and other system tasks."
    )
    parameters: dict = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The full command to run, e.g. 'ls -la ~/Documents'",
            },
        },
        "required": ["command"],
    }

    def __init__(self, allowed_commands: list[str], timeout: int = 30) -> None:
        self.allowed_commands = allowed_commands
        self.timeout = timeout

    async def run(self, **kwargs) -> str:
        command: str = kwargs.get("command", "")
        try:
            is_valid, error = validate_command(command, self.allowed_commands)
            if not is_valid:
                return f"Command rejected: {error}"

            tokens = shlex.split(command)
            proc = await asyncio.create_subprocess_exec(
                *tokens,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=self.timeout
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                return f"Command timed out after {self.timeout}s."

            output = stdout.decode("utf-8", errors="replace")
            err_output = stderr.decode("utf-8", errors="replace")

            if proc.returncode != 0 and err_output:
                result = err_output.strip()
            else:
                result = output.strip()
                if err_output.strip():
                    result += f"\n[stderr]: {err_output.strip()}"

            if len(result) > _MAX_OUTPUT:
                result = result[:_MAX_OUTPUT] + "\n\n[truncated — output exceeded 4000 chars]"

            return result if result else "(command produced no output)"

        except Exception as exc:
            logger.exception("pc_run_command failed")
            return f"Error running command: {exc}"
