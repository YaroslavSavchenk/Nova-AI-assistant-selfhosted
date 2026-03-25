"""
Tests for the cc_workflows package — store layer and all seven modules.
"""

import json
import os

import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from modules.cc_workflows._store import (
    create_workflow,
    save_workflow,
    load_workflow,
    list_workflows,
    delete_workflow,
    new_step,
    new_workflow_id,
)
from modules.cc_workflows import (
    CCWorkflowCreateModule,
    CCWorkflowAddStepModule,
    CCWorkflowListModule,
    CCWorkflowViewModule,
    CCWorkflowRunModule,
    CCWorkflowEditStepModule,
    CCWorkflowDeleteModule,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

PROJECTS = {
    "nova": {"path": "/tmp/test-nova-project"},
    "webapp": {"path": "/tmp/test-webapp"},
}


@pytest.fixture(autouse=True)
def workflows_dir(tmp_path, monkeypatch):
    """Redirect workflow storage to a temp directory."""
    monkeypatch.setattr(
        "modules.cc_workflows._store._WORKFLOWS_DIR", tmp_path
    )
    return tmp_path


@pytest.fixture
def sample_workflow():
    """Create and return a sample workflow dict (not saved)."""
    wf = create_workflow(
        title="Test workflow",
        project="nova",
        project_path="/tmp/test-nova-project",
    )
    wf["steps"] = [
        new_step(1, "Analyze the codebase"),
        new_step(2, "Write implementation"),
        new_step(3, "Write tests"),
    ]
    return wf


@pytest.fixture
def create_mod():
    return CCWorkflowCreateModule(projects=PROJECTS)


@pytest.fixture
def add_step_mod():
    return CCWorkflowAddStepModule()


@pytest.fixture
def list_mod():
    return CCWorkflowListModule()


@pytest.fixture
def view_mod():
    return CCWorkflowViewModule()


@pytest.fixture
def run_mod():
    return CCWorkflowRunModule(timeout=10)


@pytest.fixture
def edit_step_mod():
    return CCWorkflowEditStepModule()


@pytest.fixture
def delete_mod():
    return CCWorkflowDeleteModule()


# ---------------------------------------------------------------------------
# _store tests
# ---------------------------------------------------------------------------


class TestStore:
    def test_new_workflow_id_format(self):
        wf_id = new_workflow_id()
        assert wf_id.startswith("wf-")
        assert len(wf_id) == 11  # "wf-" + 8 hex chars

    def test_create_workflow_structure(self):
        wf = create_workflow("My task", "nova", "/some/path")
        assert wf["title"] == "My task"
        assert wf["project"] == "nova"
        assert wf["project_path"] == "/some/path"
        assert wf["claude_session_id"] is None
        assert wf["steps"] == []
        assert wf["id"].startswith("wf-")

    def test_new_step_structure(self):
        step = new_step(1, "Do something")
        assert step["index"] == 1
        assert step["prompt"] == "Do something"
        assert step["status"] == "pending"
        assert step["output"] is None

    @pytest.mark.asyncio
    async def test_save_and_load(self, sample_workflow, workflows_dir):
        await save_workflow(sample_workflow)
        loaded = await load_workflow(sample_workflow["id"])
        assert loaded is not None
        assert loaded["id"] == sample_workflow["id"]
        assert loaded["title"] == "Test workflow"
        assert len(loaded["steps"]) == 3

    @pytest.mark.asyncio
    async def test_load_nonexistent(self):
        result = await load_workflow("wf-nonexist")
        assert result is None

    @pytest.mark.asyncio
    async def test_list_workflows_empty(self):
        result = await list_workflows()
        assert result == []

    @pytest.mark.asyncio
    async def test_list_workflows_returns_all(self, sample_workflow):
        await save_workflow(sample_workflow)
        wf2 = create_workflow("Second", "webapp", "/tmp/test-webapp")
        await save_workflow(wf2)
        result = await list_workflows()
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_list_workflows_filter_project(self, sample_workflow):
        await save_workflow(sample_workflow)
        wf2 = create_workflow("Second", "webapp", "/tmp/test-webapp")
        await save_workflow(wf2)
        result = await list_workflows(project="nova")
        assert len(result) == 1
        assert result[0]["project"] == "nova"

    @pytest.mark.asyncio
    async def test_delete_workflow(self, sample_workflow, workflows_dir):
        await save_workflow(sample_workflow)
        assert await delete_workflow(sample_workflow["id"]) is True
        assert await load_workflow(sample_workflow["id"]) is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self):
        assert await delete_workflow("wf-nonexist") is False


# ---------------------------------------------------------------------------
# CCWorkflowCreateModule
# ---------------------------------------------------------------------------


class TestCreateModule:
    @pytest.mark.asyncio
    async def test_create_success(self, create_mod):
        with patch("modules.cc_workflows.create.os.path.isdir", return_value=True):
            result = await create_mod.run(title="New feature", project="nova")
        assert "Workflow created" in result
        assert "wf-" in result

    @pytest.mark.asyncio
    async def test_create_empty_title(self, create_mod):
        result = await create_mod.run(title="", project="nova")
        assert "Error" in result

    @pytest.mark.asyncio
    async def test_create_unknown_project(self, create_mod):
        result = await create_mod.run(title="Test", project="nonexistent")
        assert "Error" in result
        assert "unknown project" in result

    @pytest.mark.asyncio
    async def test_create_bad_project_path(self, create_mod):
        with patch("modules.cc_workflows.create.os.path.isdir", return_value=False):
            result = await create_mod.run(title="Test", project="nova")
        assert "Error" in result
        assert "does not exist" in result


# ---------------------------------------------------------------------------
# CCWorkflowAddStepModule
# ---------------------------------------------------------------------------


class TestAddStepModule:
    @pytest.mark.asyncio
    async def test_add_step_append(self, add_step_mod, sample_workflow):
        await save_workflow(sample_workflow)
        result = await add_step_mod.run(
            workflow_id=sample_workflow["id"],
            prompt="Deploy to production",
        )
        assert "Step 4 added" in result

    @pytest.mark.asyncio
    async def test_add_step_insert_at_position(self, add_step_mod, sample_workflow):
        await save_workflow(sample_workflow)
        result = await add_step_mod.run(
            workflow_id=sample_workflow["id"],
            prompt="Review code",
            position=2,
        )
        assert "Step 2 added" in result
        # Verify re-indexing
        wf = await load_workflow(sample_workflow["id"])
        assert len(wf["steps"]) == 4
        assert wf["steps"][1]["prompt"] == "Review code"
        assert wf["steps"][2]["index"] == 3  # re-numbered

    @pytest.mark.asyncio
    async def test_add_step_nonexistent_workflow(self, add_step_mod):
        result = await add_step_mod.run(
            workflow_id="wf-nonexist", prompt="test"
        )
        assert "Error" in result
        assert "not found" in result

    @pytest.mark.asyncio
    async def test_add_step_empty_prompt(self, add_step_mod, sample_workflow):
        await save_workflow(sample_workflow)
        result = await add_step_mod.run(
            workflow_id=sample_workflow["id"], prompt=""
        )
        assert "Error" in result


# ---------------------------------------------------------------------------
# CCWorkflowListModule
# ---------------------------------------------------------------------------


class TestListModule:
    @pytest.mark.asyncio
    async def test_list_empty(self, list_mod):
        result = await list_mod.run()
        assert "No workflows found" in result

    @pytest.mark.asyncio
    async def test_list_with_workflows(self, list_mod, sample_workflow):
        await save_workflow(sample_workflow)
        result = await list_mod.run()
        assert "1 workflow" in result
        assert sample_workflow["id"] in result

    @pytest.mark.asyncio
    async def test_list_filter_project(self, list_mod, sample_workflow):
        await save_workflow(sample_workflow)
        result = await list_mod.run(project="webapp")
        assert "No workflows found" in result


# ---------------------------------------------------------------------------
# CCWorkflowViewModule
# ---------------------------------------------------------------------------


class TestViewModule:
    @pytest.mark.asyncio
    async def test_view_success(self, view_mod, sample_workflow):
        await save_workflow(sample_workflow)
        result = await view_mod.run(workflow_id=sample_workflow["id"])
        assert "Test workflow" in result
        assert "Step 1" in result
        assert "Step 2" in result
        assert "Step 3" in result

    @pytest.mark.asyncio
    async def test_view_nonexistent(self, view_mod):
        result = await view_mod.run(workflow_id="wf-nonexist")
        assert "Error" in result

    @pytest.mark.asyncio
    async def test_view_with_output(self, view_mod, sample_workflow):
        sample_workflow["steps"][0]["status"] = "done"
        sample_workflow["steps"][0]["output"] = "Some output text here"
        await save_workflow(sample_workflow)
        result = await view_mod.run(workflow_id=sample_workflow["id"])
        assert "Some output text here" in result
        assert "[x]" in result  # done icon


# ---------------------------------------------------------------------------
# CCWorkflowEditStepModule
# ---------------------------------------------------------------------------


class TestEditStepModule:
    @pytest.mark.asyncio
    async def test_edit_pending_step(self, edit_step_mod, sample_workflow):
        await save_workflow(sample_workflow)
        result = await edit_step_mod.run(
            workflow_id=sample_workflow["id"],
            step=2,
            prompt="New prompt text",
        )
        assert "updated" in result
        wf = await load_workflow(sample_workflow["id"])
        assert wf["steps"][1]["prompt"] == "New prompt text"

    @pytest.mark.asyncio
    async def test_edit_done_step_rejected(self, edit_step_mod, sample_workflow):
        sample_workflow["steps"][0]["status"] = "done"
        await save_workflow(sample_workflow)
        result = await edit_step_mod.run(
            workflow_id=sample_workflow["id"],
            step=1,
            prompt="New prompt",
        )
        assert "Error" in result
        assert "pending" in result

    @pytest.mark.asyncio
    async def test_edit_nonexistent_step(self, edit_step_mod, sample_workflow):
        await save_workflow(sample_workflow)
        result = await edit_step_mod.run(
            workflow_id=sample_workflow["id"],
            step=99,
            prompt="New prompt",
        )
        assert "Error" in result
        assert "not found" in result


# ---------------------------------------------------------------------------
# CCWorkflowDeleteModule
# ---------------------------------------------------------------------------


class TestDeleteModule:
    @pytest.mark.asyncio
    async def test_delete_success(self, delete_mod, sample_workflow):
        await save_workflow(sample_workflow)
        result = await delete_mod.run(workflow_id=sample_workflow["id"])
        assert "deleted" in result
        assert await load_workflow(sample_workflow["id"]) is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self, delete_mod):
        result = await delete_mod.run(workflow_id="wf-nonexist")
        assert "Error" in result
        assert "not found" in result


# ---------------------------------------------------------------------------
# CCWorkflowRunModule
# ---------------------------------------------------------------------------


class TestRunModule:
    @pytest.mark.asyncio
    async def test_run_no_steps(self, run_mod):
        wf = create_workflow("Empty", "nova", "/tmp/test-nova-project")
        await save_workflow(wf)
        result = await run_mod.run(workflow_id=wf["id"])
        assert "no steps" in result

    @pytest.mark.asyncio
    async def test_run_nonexistent_workflow(self, run_mod):
        result = await run_mod.run(workflow_id="wf-nonexist")
        assert "Error" in result
        assert "not found" in result

    @pytest.mark.asyncio
    async def test_run_all_done(self, run_mod, sample_workflow):
        for s in sample_workflow["steps"]:
            s["status"] = "done"
        await save_workflow(sample_workflow)
        result = await run_mod.run(workflow_id=sample_workflow["id"])
        assert "complete" in result
        assert "No pending" in result

    @pytest.mark.asyncio
    async def test_run_specific_step_not_found(self, run_mod, sample_workflow):
        await save_workflow(sample_workflow)
        result = await run_mod.run(
            workflow_id=sample_workflow["id"], step=99
        )
        assert "Error" in result
        assert "not found" in result

    @pytest.mark.asyncio
    async def test_run_no_claude_cli(self, run_mod, sample_workflow):
        await save_workflow(sample_workflow)
        with patch("modules.cc_workflows.run._find_claude_cli", return_value=None), \
             patch("modules.cc_workflows.run.os.path.isdir", return_value=True):
            result = await run_mod.run(workflow_id=sample_workflow["id"])
        assert "Error" in result
        assert "not found" in result

    @pytest.mark.asyncio
    async def test_run_bad_project_path(self, run_mod, sample_workflow):
        sample_workflow["project_path"] = "/nonexistent/path"
        await save_workflow(sample_workflow)
        result = await run_mod.run(workflow_id=sample_workflow["id"])
        assert "Error" in result
        assert "does not exist" in result

    @pytest.mark.asyncio
    async def test_run_success_first_step(self, run_mod, sample_workflow):
        await save_workflow(sample_workflow)

        mock_proc = AsyncMock()
        mock_proc.returncode = 0

        # Simulate stdout that yields lines then EOF
        stdout_lines = [b"Line 1\n", b"Line 2\n", b"Done\n"]
        stdout_iter = iter(stdout_lines)

        async def mock_readline_stdout():
            try:
                return next(stdout_iter)
            except StopIteration:
                return b""

        mock_proc.stdout = MagicMock()
        mock_proc.stdout.readline = mock_readline_stdout

        # Empty stderr
        async def mock_readline_stderr():
            return b""

        mock_proc.stderr = MagicMock()
        mock_proc.stderr.readline = mock_readline_stderr

        mock_proc.wait = AsyncMock()

        with patch("modules.cc_workflows.run._find_claude_cli", return_value="/usr/bin/claude"), \
             patch("modules.cc_workflows.run.os.path.isdir", return_value=True), \
             patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
            result = await run_mod.run(workflow_id=sample_workflow["id"])

        assert "completed" in result
        assert "1/3" in result

        # Verify first step does NOT use --continue
        call_args = mock_exec.call_args[0]
        assert "--continue" not in call_args

        # Verify step status persisted
        wf = await load_workflow(sample_workflow["id"])
        assert wf["steps"][0]["status"] == "done"
        assert wf["steps"][0]["output"] is not None

    @pytest.mark.asyncio
    async def test_run_uses_continue_after_first(self, run_mod, sample_workflow):
        # Mark first step as done
        sample_workflow["steps"][0]["status"] = "done"
        sample_workflow["steps"][0]["output"] = "done"
        await save_workflow(sample_workflow)

        mock_proc = AsyncMock()
        mock_proc.returncode = 0

        async def mock_readline_empty():
            return b""

        mock_proc.stdout = MagicMock()
        mock_proc.stdout.readline = mock_readline_empty
        mock_proc.stderr = MagicMock()
        mock_proc.stderr.readline = mock_readline_empty
        mock_proc.wait = AsyncMock()

        with patch("modules.cc_workflows.run._find_claude_cli", return_value="/usr/bin/claude"), \
             patch("modules.cc_workflows.run.os.path.isdir", return_value=True), \
             patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
            result = await run_mod.run(workflow_id=sample_workflow["id"])

        # Verify --continue IS used for non-first step
        call_args = mock_exec.call_args[0]
        assert "--continue" in call_args

    @pytest.mark.asyncio
    async def test_run_failed_step(self, run_mod, sample_workflow):
        await save_workflow(sample_workflow)

        mock_proc = AsyncMock()
        mock_proc.returncode = 1

        async def mock_readline_empty():
            return b""

        mock_proc.stdout = MagicMock()
        mock_proc.stdout.readline = mock_readline_empty
        mock_proc.stderr = MagicMock()
        mock_proc.stderr.readline = mock_readline_empty
        mock_proc.wait = AsyncMock()

        with patch("modules.cc_workflows.run._find_claude_cli", return_value="/usr/bin/claude"), \
             patch("modules.cc_workflows.run.os.path.isdir", return_value=True), \
             patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await run_mod.run(workflow_id=sample_workflow["id"])

        assert "FAILED" in result
        wf = await load_workflow(sample_workflow["id"])
        assert wf["steps"][0]["status"] == "failed"

    @pytest.mark.asyncio
    async def test_run_empty_workflow_id(self, run_mod):
        result = await run_mod.run(workflow_id="")
        assert "Error" in result
