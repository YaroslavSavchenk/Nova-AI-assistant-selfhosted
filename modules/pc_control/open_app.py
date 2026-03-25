"""PC control — open a Windows or Linux application, file, or URL from WSL2."""

import asyncio
import logging
import os
import shutil

from modules.base import NovaModule

logger = logging.getLogger(__name__)

# A safe CWD for cmd.exe — UNC paths (\\wsl.localhost\...) are not supported.
_WIN_SAFE_CWD = "/mnt/c/Windows"

# Mapping of friendly names → Windows executables or commands.
# Keys are lowercased for matching.  Values are passed to cmd.exe /c start.
_APP_SHORTCUTS: dict[str, list[str]] = {
    # Editors
    "vscode": ["code"],
    "code": ["code"],
    "notepad": ["notepad.exe"],
    "notepad++": ["notepad++.exe"],
    # Browsers
    "browser": ["cmd.exe", "/c", "start", "http://"],
    "chrome": ["cmd.exe", "/c", "start", "chrome"],
    "firefox": ["cmd.exe", "/c", "start", "firefox"],
    "edge": ["cmd.exe", "/c", "start", "msedge"],
    # System
    "explorer": ["explorer.exe"],
    "file explorer": ["explorer.exe"],
    "terminal": ["wt.exe"],
    "windows terminal": ["wt.exe"],
    "task manager": ["taskmgr.exe"],
    "taskmgr": ["taskmgr.exe"],
    "settings": ["cmd.exe", "/c", "start", "ms-settings:"],
    "control panel": ["control.exe"],
    # Utilities
    "calculator": ["calc.exe"],
    "calc": ["calc.exe"],
    "paint": ["mspaint.exe"],
    "snipping tool": ["snippingtool.exe"],
    # Common apps (these use cmd.exe /c start to resolve Start Menu shortcuts)
    "claude": ["cmd.exe", "/c", "start", "claude:"],
    "claude app": ["cmd.exe", "/c", "start", "claude:"],
    "spotify": ["cmd.exe", "/c", "start", "spotify:"],
    "discord": ["cmd.exe", "/c", "start", "discord:"],
    "steam": ["cmd.exe", "/c", "start", "steam://open/main"],
    "teams": ["cmd.exe", "/c", "start", "msteams:"],
    "outlook": ["cmd.exe", "/c", "start", "outlook:"],
    "word": ["cmd.exe", "/c", "start", "winword"],
    "excel": ["cmd.exe", "/c", "start", "excel"],
    "powerpoint": ["cmd.exe", "/c", "start", "powerpnt"],
}


class OpenAppModule(NovaModule):
    name: str = "pc_open_app"
    description: str = (
        "Open a Windows or Linux application, file, or URL. "
        "Can open apps like VS Code, Chrome, Spotify, File Explorer, "
        "or any installed Windows program by name."
    )
    parameters: dict = {
        "type": "object",
        "properties": {
            "target": {
                "type": "string",
                "description": (
                    "Application name (e.g. 'chrome', 'spotify', 'vscode', "
                    "'task manager'), file path, or URL to open"
                ),
            },
        },
        "required": ["target"],
    }

    async def run(self, **kwargs) -> str:
        target: str = kwargs.get("target", "").strip()

        if not target:
            return "Error: target cannot be empty."

        try:
            # URLs — open in default Windows browser
            if target.startswith("http://") or target.startswith("https://"):
                return await self._exec(
                    ["cmd.exe", "/c", "start", "", target], target
                )

            # Known app shortcuts (case-insensitive)
            lower_target = target.lower()
            if lower_target in _APP_SHORTCUTS:
                cmd = _APP_SHORTCUTS[lower_target]
                return await self._exec(cmd, target)

            # Try as a direct executable (e.g. "notepad.exe", "code")
            if shutil.which(target):
                return await self._exec([target], target)

            # Fallback — ask Windows to open it via cmd.exe /c start
            # This handles Start Menu apps, registered protocols, file paths, etc.
            return await self._exec(
                ["cmd.exe", "/c", "start", "", target], target
            )

        except FileNotFoundError:
            return (
                f"Error: could not find a handler to open '{target}'. "
                f"Make sure the application is installed."
            )
        except Exception as exc:
            logger.exception("pc_open_app failed")
            return f"Error opening '{target}': {exc}"

    async def _exec(self, cmd: list[str], target: str) -> str:
        """Run the open command and return a confirmation or error."""
        # cmd.exe chokes on UNC paths as CWD — use a Windows-safe directory.
        cwd = _WIN_SAFE_CWD if cmd[0] == "cmd.exe" else None
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
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
