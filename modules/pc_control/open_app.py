"""PC control — open an application, file, or URL."""

import asyncio
import logging

from modules.base import NovaModule

logger = logging.getLogger(__name__)

# Known application shortcuts → actual commands
_APP_SHORTCUTS: dict[str, str] = {
    "vscode": "code",
    "code": "code",
    "explorer": "explorer.exe",
    "file explorer": "explorer.exe",
    "browser": "wslview",
    "terminal": "wt.exe",
}


class OpenAppModule(NovaModule):
    name: str = "pc_open_app"
    description: str = (
        "Open an application, file, or URL. "
        "Works with both Linux and Windows applications on WSL2."
    )
    parameters: dict = {
        "type": "object",
        "properties": {
            "target": {
                "type": "string",
                "description": "Application name, file path, or URL to open",
            },
        },
        "required": ["target"],
    }

    async def run(self, **kwargs) -> str:
        target: str = kwargs.get("target", "").strip()

        if not target:
            return "Error: target cannot be empty."

        try:
            # URLs — open in default browser via wslview
            if target.startswith("http://") or target.startswith("https://"):
                return await self._exec(["wslview", target], target)

            # Known app shortcuts
            lower_target = target.lower()
            if lower_target in _APP_SHORTCUTS:
                cmd = _APP_SHORTCUTS[lower_target]
                return await self._exec([cmd], target)

            # Fallback — use wslview for files and anything else
            return await self._exec(["wslview", target], target)

        except FileNotFoundError:
            return f"Error: could not find a handler to open '{target}'. Is wslview installed?"
        except Exception as exc:
            logger.exception("pc_open_app failed")
            return f"Error opening '{target}': {exc}"

    async def _exec(self, cmd: list[str], target: str) -> str:
        """Run the open command and return a confirmation or error."""
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return f"Timed out trying to open '{target}'."

        if proc.returncode != 0:
            err = stderr.decode("utf-8", errors="replace").strip()
            return f"Failed to open '{target}': {err}" if err else f"Failed to open '{target}'."

        return f"Opened {target}"
