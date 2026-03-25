"""CC Workflow — add a step to an existing workflow."""

import logging

from modules.base import NovaModule
from modules.cc_workflows._store import load_workflow, save_workflow, new_step

logger = logging.getLogger(__name__)


class CCWorkflowAddStepModule(NovaModule):
    name: str = "cc_workflow_add_step"
    description: str = (
        "Add a new step (Claude Code prompt) to an existing workflow. "
        "Steps are executed in order. Optionally insert at a specific position."
    )
    parameters: dict = {
        "type": "object",
        "properties": {
            "workflow_id": {
                "type": "string",
                "description": "The workflow ID (e.g. wf-abc12345)",
            },
            "prompt": {
                "type": "string",
                "description": "The prompt to send to Claude Code for this step",
            },
            "position": {
                "type": "integer",
                "description": (
                    "Insert at this position (1-based). If omitted, appends to the end."
                ),
            },
        },
        "required": ["workflow_id", "prompt"],
    }

    async def run(self, **kwargs) -> str:
        wf_id: str = kwargs.get("workflow_id", "").strip()
        prompt: str = kwargs.get("prompt", "").strip()
        position: int | None = kwargs.get("position")

        if not wf_id:
            return "Error: workflow_id is required."
        if not prompt:
            return "Error: prompt cannot be empty."

        try:
            wf = await load_workflow(wf_id)
            if wf is None:
                return f"Error: workflow '{wf_id}' not found."

            steps = wf["steps"]

            if position is not None:
                # Clamp to valid range
                pos = max(1, min(position, len(steps) + 1))
                insert_idx = pos - 1
                step = new_step(index=pos, prompt=prompt)
                steps.insert(insert_idx, step)
                # Re-number all steps
                for i, s in enumerate(steps):
                    s["index"] = i + 1
            else:
                step = new_step(index=len(steps) + 1, prompt=prompt)
                steps.append(step)

            await save_workflow(wf)

            step_num = step["index"]
            total = len(steps)
            return (
                f"Step {step_num} added to workflow '{wf_id}' ({total} total steps).\n"
                f"  Prompt: {prompt[:100]}{'...' if len(prompt) > 100 else ''}"
            )
        except Exception as exc:
            logger.exception("cc_workflow_add_step failed")
            return f"Error adding step: {exc}"
