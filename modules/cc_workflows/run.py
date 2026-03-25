"""CC Workflow — run the next (or a specific) step in a workflow."""

import asyncio
import logging
import os
import shutil
import sys
from datetime import datetime, timezone

from modules.base import NovaModule
from modules.cc_workflows._store import load_workflow, save_workflow

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


class CCWorkflowRunModule(NovaModule):
    name: str = "cc_workflow_run"
    description: str = (
        "Run the next pending step (or a specific step) in a Claude Code workflow. "
        "Output is streamed to the terminal in real-time. Uses --continue for "
        "session continuity across steps."
    )
    parameters: dict = {
        "type": "object",
        "properties": {
            "workflow_id": {
                "type": "string",
                "description": "The workflow ID to run",
            },
            "step": {
                "type": "integer",
                "description": (
                    "Run a specific step number (1-based). "
                    "If omitted, runs the next pending step."
                ),
            },
        },
        "required": ["workflow_id"],
    }

    def __init__(self, timeout: int = 300) -> None:
        self.timeout = timeout

    async def run(self, **kwargs) -> str:
        wf_id: str = kwargs.get("workflow_id", "").strip()
        step_num: int | None = kwargs.get("step")

        if not wf_id:
            return "Error: workflow_id is required."

        try:
            wf = await load_workflow(wf_id)
            if wf is None:
                return f"Error: workflow '{wf_id}' not found."

            steps = wf.get("steps", [])
            if not steps:
                return f"Workflow '{wf_id}' has no steps. Add steps first."

            # Find the target step
            if step_num is not None:
                target = next((s for s in steps if s["index"] == step_num), None)
                if target is None:
                    return f"Error: step {step_num} not found in workflow '{wf_id}'."
            else:
                # Find next pending step
                target = next((s for s in steps if s["status"] == "pending"), None)
                if target is None:
                    done = sum(1 for s in steps if s["status"] == "done")
                    return (
                        f"All {len(steps)} steps in workflow '{wf_id}' are complete "
                        f"({done} done). No pending steps."
                    )

            # Validate project path still exists
            cwd = wf.get("project_path", "")
            if not os.path.isdir(cwd):
                return f"Error: project path '{cwd}' does not exist."

            # Find claude CLI
            claude_bin = _find_claude_cli()
            if not claude_bin:
                return "Error: 'claude' CLI not found. Is Claude Code installed?"

            # Build command
            cmd = [claude_bin, "-p", target["prompt"]]

            # Use --continue for session continuity (after first step)
            is_first_step = all(s["status"] == "pending" for s in steps)
            if not is_first_step:
                cmd.append("--continue")

            # Mark step as running
            target["status"] = "running"
            target["started_at"] = datetime.now(timezone.utc).isoformat()
            await save_workflow(wf)

            # Run with real-time output streaming
            output_lines: list[str] = []
            return_code: int = -1

            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=cwd,
                )

                async def _read_stream(stream, lines_list, file_out):
                    """Read stream line by line, printing in real-time."""
                    while True:
                        line = await stream.readline()
                        if not line:
                            break
                        decoded = line.decode("utf-8", errors="replace")
                        lines_list.append(decoded)
                        # Print to terminal in real-time
                        print(decoded, end="", flush=True, file=file_out)

                stderr_lines: list[str] = []

                try:
                    await asyncio.wait_for(
                        asyncio.gather(
                            _read_stream(proc.stdout, output_lines, sys.stdout),
                            _read_stream(proc.stderr, stderr_lines, sys.stderr),
                        ),
                        timeout=self.timeout,
                    )
                    await proc.wait()
                    return_code = proc.returncode
                except asyncio.TimeoutError:
                    proc.kill()
                    await proc.wait()
                    target["status"] = "failed"
                    target["completed_at"] = datetime.now(timezone.utc).isoformat()
                    target["output"] = "".join(output_lines) or "(timed out)"
                    await save_workflow(wf)
                    return (
                        f"Step {target['index']} timed out after {self.timeout}s. "
                        f"Captured {len(output_lines)} lines before timeout."
                    )

            except FileNotFoundError:
                target["status"] = "failed"
                target["completed_at"] = datetime.now(timezone.utc).isoformat()
                target["output"] = "claude CLI not found"
                await save_workflow(wf)
                return "Error: 'claude' CLI not found."

            # Collect output
            full_output = "".join(output_lines).strip()
            now = datetime.now(timezone.utc).isoformat()

            if return_code == 0:
                target["status"] = "done"
            else:
                target["status"] = "failed"

            target["completed_at"] = now

            # Store output (truncated for storage)
            if len(full_output) > _MAX_OUTPUT:
                target["output"] = (
                    full_output[:_MAX_OUTPUT]
                    + "\n\n[truncated — output exceeded 6000 chars]"
                )
            else:
                target["output"] = full_output if full_output else "(no output)"

            await save_workflow(wf)

            # Build summary (user already saw full output in real-time)
            done_count = sum(1 for s in steps if s["status"] == "done")
            total = len(steps)
            status_word = "completed" if target["status"] == "done" else "FAILED"

            # Show first and last few lines as summary
            summary_lines = []
            if full_output:
                lines = full_output.split("\n")
                if len(lines) <= 6:
                    summary_lines = lines
                else:
                    summary_lines = lines[:3] + ["  ..."] + lines[-3:]

            summary = "\n".join(summary_lines) if summary_lines else "(no output)"

            return (
                f"Step {target['index']} {status_word}. "
                f"Progress: {done_count}/{total} steps done.\n\n"
                f"Output summary:\n{summary}"
            )

        except Exception as exc:
            logger.exception("cc_workflow_run failed")
            return f"Error running workflow step: {exc}"
