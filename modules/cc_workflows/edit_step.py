"""CC Workflow — edit a pending step's prompt."""

import logging

from modules.base import NovaModule
from modules.cc_workflows._store import load_workflow, save_workflow

logger = logging.getLogger(__name__)


class CCWorkflowEditStepModule(NovaModule):
    name: str = "cc_workflow_edit_step"
    description: str = (
        "Edit the prompt of a pending step in a workflow. "
        "Only steps with status 'pending' can be edited."
    )
    parameters: dict = {
        "type": "object",
        "properties": {
            "workflow_id": {
                "type": "string",
                "description": "The workflow ID",
            },
            "step": {
                "type": "integer",
                "description": "Step number to edit (1-based)",
            },
            "prompt": {
                "type": "string",
                "description": "New prompt text for the step",
            },
        },
        "required": ["workflow_id", "step", "prompt"],
    }

    async def run(self, **kwargs) -> str:
        wf_id: str = kwargs.get("workflow_id", "").strip()
        step_num: int = kwargs.get("step", 0)
        prompt: str = kwargs.get("prompt", "").strip()

        if not wf_id:
            return "Error: workflow_id is required."
        if not step_num:
            return "Error: step number is required."
        if not prompt:
            return "Error: prompt cannot be empty."

        try:
            wf = await load_workflow(wf_id)
            if wf is None:
                return f"Error: workflow '{wf_id}' not found."

            target = next(
                (s for s in wf["steps"] if s["index"] == step_num), None
            )
            if target is None:
                return f"Error: step {step_num} not found in workflow '{wf_id}'."

            if target["status"] != "pending":
                return (
                    f"Error: step {step_num} has status '{target['status']}'. "
                    f"Only pending steps can be edited."
                )

            old_prompt = target["prompt"]
            target["prompt"] = prompt
            await save_workflow(wf)

            return (
                f"Step {step_num} updated in workflow '{wf_id}'.\n"
                f"  Old: {old_prompt[:80]}{'...' if len(old_prompt) > 80 else ''}\n"
                f"  New: {prompt[:80]}{'...' if len(prompt) > 80 else ''}"
            )
        except Exception as exc:
            logger.exception("cc_workflow_edit_step failed")
            return f"Error editing step: {exc}"
