"""PC control — read the contents of a local file."""

import asyncio
import logging
import os

from modules.base import NovaModule
from modules.pc_control._safety import sanitize_path

logger = logging.getLogger(__name__)

_MAX_FILE_SIZE = 100 * 1024  # 100 KB


class ReadFileModule(NovaModule):
    name: str = "pc_read_file"
    description: str = (
        "Read the contents of a local file. "
        "Use for viewing config files, notes, code, or any text file."
    )
    parameters: dict = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to the file to read",
            },
            "max_lines": {
                "type": "integer",
                "description": "Maximum number of lines to return (default: 100)",
            },
        },
        "required": ["path"],
    }

    async def run(self, **kwargs) -> str:
        raw_path: str = kwargs.get("path", "")
        max_lines: int = int(kwargs.get("max_lines", 100))

        if not raw_path.strip():
            return "Error: path cannot be empty."

        try:
            resolved = sanitize_path(raw_path)

            if not os.path.exists(resolved):
                return f"File not found: {resolved}"
            if os.path.isdir(resolved):
                return f"'{resolved}' is a directory, not a file. Use pc_run_command with 'ls' instead."
            if not os.access(resolved, os.R_OK):
                return f"Permission denied: cannot read '{resolved}'."

            file_size = os.path.getsize(resolved)
            if file_size > _MAX_FILE_SIZE:
                return (
                    f"File is too large ({file_size:,} bytes, limit is {_MAX_FILE_SIZE:,}). "
                    f"Try setting max_lines to read a portion of the file."
                )

            content = await asyncio.to_thread(self._read_file, resolved, max_lines)
            return content

        except Exception as exc:
            logger.exception("pc_read_file failed")
            return f"Error reading file: {exc}"

    @staticmethod
    def _read_file(path: str, max_lines: int) -> str:
        """Read a file synchronously (called via asyncio.to_thread)."""
        # Try utf-8 first, fall back to latin-1
        for encoding in ("utf-8", "latin-1"):
            try:
                with open(path, "r", encoding=encoding) as f:
                    lines = []
                    for i, line in enumerate(f):
                        if i >= max_lines:
                            lines.append(
                                f"\n[truncated — showing first {max_lines} of file]"
                            )
                            break
                        lines.append(line)
                return "".join(lines)
            except UnicodeDecodeError:
                continue

        return "Error: could not decode file with utf-8 or latin-1 encoding."
