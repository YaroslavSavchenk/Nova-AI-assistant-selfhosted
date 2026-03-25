"""PC control — write or append content to a local file."""

import asyncio
import logging
import os

from modules.base import NovaModule
from modules.pc_control._safety import sanitize_path, is_path_writable

logger = logging.getLogger(__name__)


class WriteFileModule(NovaModule):
    name: str = "pc_write_file"
    description: str = (
        "Write or append content to a local file. "
        "Restricted to configured writable directories for safety."
    )
    parameters: dict = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to the file to write",
            },
            "content": {
                "type": "string",
                "description": "Content to write to the file",
            },
            "mode": {
                "type": "string",
                "enum": ["write", "append"],
                "description": "Write mode: 'write' to overwrite, 'append' to add to end (default: 'write')",
            },
        },
        "required": ["path", "content"],
    }

    def __init__(self, writable_dirs: list[str]) -> None:
        self.writable_dirs = writable_dirs

    async def run(self, **kwargs) -> str:
        raw_path: str = kwargs.get("path", "")
        content: str = kwargs.get("content", "")
        mode: str = kwargs.get("mode", "write")

        if not raw_path.strip():
            return "Error: path cannot be empty."

        if mode not in ("write", "append"):
            return f"Error: invalid mode '{mode}'. Must be 'write' or 'append'."

        try:
            resolved = sanitize_path(raw_path)

            if not is_path_writable(resolved, self.writable_dirs):
                allowed = ", ".join(self.writable_dirs)
                return (
                    f"Write rejected: '{resolved}' is not under an allowed writable directory. "
                    f"Allowed directories: {allowed}"
                )

            await asyncio.to_thread(self._write_file, resolved, content, mode)

            n_bytes = len(content.encode("utf-8"))
            action = "Wrote" if mode == "write" else "Appended"
            return f"{action} {n_bytes} bytes to {resolved}"

        except Exception as exc:
            logger.exception("pc_write_file failed")
            return f"Error writing file: {exc}"

    @staticmethod
    def _write_file(path: str, content: str, mode: str) -> None:
        """Write a file synchronously (called via asyncio.to_thread)."""
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)

        file_mode = "w" if mode == "write" else "a"
        with open(path, file_mode, encoding="utf-8") as f:
            f.write(content)
