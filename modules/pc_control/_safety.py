"""Shared safety utilities for PC control modules."""

import os
import shlex
from pathlib import Path


# Shell injection patterns that must never appear in commands
_INJECTION_PATTERNS = (";", "|", "&&", "||", "$(", "`", ">", "<", "\n")


def validate_command(command: str, allowed_commands: list[str]) -> tuple[bool, str]:
    """
    Parse the first token of *command* and check it against the allowlist.
    Also rejects shell injection patterns.

    Returns:
        (is_valid, error_message) — error_message is empty when valid.
    """
    if not command or not command.strip():
        return False, "Empty command."

    # Check for shell injection patterns in the raw command string
    for pattern in _INJECTION_PATTERNS:
        if pattern in command:
            return False, f"Blocked: command contains disallowed pattern '{pattern}'."

    try:
        tokens = shlex.split(command)
    except ValueError as exc:
        return False, f"Failed to parse command: {exc}"

    if not tokens:
        return False, "Empty command after parsing."

    executable = tokens[0]

    # Strip any path prefix — only the basename matters
    executable = os.path.basename(executable)

    if executable not in allowed_commands:
        return False, (
            f"Command '{executable}' is not in the allowed list. "
            f"Allowed: {', '.join(sorted(allowed_commands))}"
        )

    return True, ""


def sanitize_path(path: str) -> str:
    """Expand ``~``, resolve to absolute, and normalize *path*."""
    return str(Path(path).expanduser().resolve())


def resolve_project(name: str, projects: dict) -> tuple[str | None, dict | None]:
    """Fuzzy-match a project name: exact → case-insensitive → substring.

    Returns (resolved_key, project_info) or (None, None) if not found.
    """
    if not name or not projects:
        return None, None
    # Exact match
    if name in projects:
        return name, projects[name]
    # Case-insensitive
    lower = name.lower().strip()
    for key, info in projects.items():
        if key.lower() == lower:
            return key, info
    # Substring / contains (e.g. "nova project" contains "nova")
    for key, info in projects.items():
        if key.lower() in lower or lower in key.lower():
            return key, info
    return None, None


def is_path_writable(path: str, writable_dirs: list[str]) -> bool:
    """Return True if *path* falls under one of the allowed writable directories."""
    resolved = Path(sanitize_path(path))
    for allowed in writable_dirs:
        allowed_resolved = Path(sanitize_path(allowed))
        try:
            resolved.relative_to(allowed_resolved)
            return True
        except ValueError:
            continue
    return False
