"""Workflow persistence layer — load/save workflow JSON files."""

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_WORKFLOWS_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "workflows"


def _ensure_dir() -> None:
    """Create the workflows directory if it doesn't exist."""
    _WORKFLOWS_DIR.mkdir(parents=True, exist_ok=True)


def _workflow_path(wf_id: str) -> Path:
    return _WORKFLOWS_DIR / f"{wf_id}.json"


def new_workflow_id() -> str:
    return f"wf-{uuid.uuid4().hex[:8]}"


def new_step(index: int, prompt: str) -> dict[str, Any]:
    """Return a fresh step dict."""
    return {
        "index": index,
        "prompt": prompt,
        "status": "pending",
        "output": None,
        "started_at": None,
        "completed_at": None,
    }


def create_workflow(title: str, project: str, project_path: str) -> dict[str, Any]:
    """Build a new workflow dict (not yet saved)."""
    now = datetime.now(timezone.utc).isoformat()
    return {
        "id": new_workflow_id(),
        "title": title,
        "project": project,
        "project_path": project_path,
        "claude_session_id": None,
        "created_at": now,
        "updated_at": now,
        "steps": [],
    }


async def save_workflow(wf: dict[str, Any]) -> None:
    """Persist a workflow dict to disk."""
    _ensure_dir()
    wf["updated_at"] = datetime.now(timezone.utc).isoformat()
    path = _workflow_path(wf["id"])
    data = json.dumps(wf, indent=2)
    await asyncio.to_thread(path.write_text, data, "utf-8")


async def load_workflow(wf_id: str) -> dict[str, Any] | None:
    """Load a workflow by ID. Returns None if not found."""
    path = _workflow_path(wf_id)
    if not path.exists():
        return None
    text = await asyncio.to_thread(path.read_text, "utf-8")
    return json.loads(text)


async def list_workflows(project: str | None = None) -> list[dict[str, Any]]:
    """List all workflows, optionally filtered by project key."""
    _ensure_dir()
    workflows: list[dict[str, Any]] = []

    def _scan() -> list[dict[str, Any]]:
        result = []
        for f in _WORKFLOWS_DIR.glob("wf-*.json"):
            try:
                data = json.loads(f.read_text("utf-8"))
                result.append(data)
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Skipping corrupt workflow file %s: %s", f, exc)
        return result

    workflows = await asyncio.to_thread(_scan)

    if project:
        lower = project.lower()
        workflows = [w for w in workflows if w.get("project", "").lower() == lower]

    # Sort newest first
    workflows.sort(key=lambda w: w.get("created_at", ""), reverse=True)
    return workflows


async def delete_workflow(wf_id: str) -> bool:
    """Delete a workflow file. Returns True if deleted, False if not found."""
    path = _workflow_path(wf_id)
    if not path.exists():
        return False
    await asyncio.to_thread(path.unlink)
    return True
