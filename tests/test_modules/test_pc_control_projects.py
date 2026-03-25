"""
Tests for the project registry and project notes modules.
"""

import os

import pytest
from unittest.mock import patch, AsyncMock

from modules.pc_control import (
    ListProjectsModule,
    ClaudeCodeModule,
    ProjectNotesReadModule,
    ProjectNotesWriteModule,
)


SAMPLE_PROJECTS = {
    "nova": {
        "path": "~/projects/Nova-AI-assistant-selfhosted",
        "description": "Personal AI assistant",
    },
    "webapp": {
        "path": "~/projects/webapp",
        "description": "Web application project",
    },
}


# ---------------------------------------------------------------------------
# ListProjectsModule
# ---------------------------------------------------------------------------


class TestListProjectsModule:
    @pytest.fixture
    def module(self):
        return ListProjectsModule(projects=SAMPLE_PROJECTS)

    @pytest.fixture
    def empty_module(self):
        return ListProjectsModule(projects={})

    @pytest.mark.asyncio
    async def test_contract(self, module):
        assert module.name == "pc_list_projects"

    @pytest.mark.asyncio
    async def test_lists_projects(self, module):
        result = await module.run()
        assert "nova" in result
        assert "webapp" in result
        assert "Personal AI assistant" in result

    @pytest.mark.asyncio
    async def test_empty_projects(self, empty_module):
        result = await empty_module.run()
        assert "No projects registered" in result


# ---------------------------------------------------------------------------
# ClaudeCodeModule — project parameter
# ---------------------------------------------------------------------------


class TestClaudeCodeModuleProject:
    @pytest.fixture
    def module(self):
        return ClaudeCodeModule(projects=SAMPLE_PROJECTS)

    @pytest.mark.asyncio
    async def test_project_resolves_to_cwd(self, module):
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"output", b""))
        mock_proc.returncode = 0

        with patch("modules.pc_control.claude_code._find_claude_cli", return_value="/usr/bin/claude"):
            with patch("modules.pc_control.claude_code.asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
                with patch("os.path.isdir", return_value=True):
                    result = await module.run(prompt="hello", project="nova")

        # Verify cwd was set to the expanded project path
        call_kwargs = mock_exec.call_args
        expected_path = os.path.expanduser("~/projects/Nova-AI-assistant-selfhosted")
        assert call_kwargs.kwargs.get("cwd") == expected_path
        assert "output" in result

    @pytest.mark.asyncio
    async def test_unknown_project_returns_error(self, module):
        result = await module.run(prompt="hello", project="nonexistent")
        assert "unknown project" in result.lower()
        assert "nonexistent" in result

    @pytest.mark.asyncio
    async def test_project_takes_precedence_over_working_directory(self, module):
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"output", b""))
        mock_proc.returncode = 0

        with patch("modules.pc_control.claude_code._find_claude_cli", return_value="/usr/bin/claude"):
            with patch("modules.pc_control.claude_code.asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
                with patch("os.path.isdir", return_value=True):
                    await module.run(prompt="hello", project="nova", working_directory="/tmp")

        call_kwargs = mock_exec.call_args
        expected_path = os.path.expanduser("~/projects/Nova-AI-assistant-selfhosted")
        assert call_kwargs.kwargs.get("cwd") == expected_path

    @pytest.mark.asyncio
    async def test_no_project_no_projects_dict(self):
        """Module works without projects (backward compatible)."""
        module = ClaudeCodeModule()
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"output", b""))
        mock_proc.returncode = 0

        with patch("modules.pc_control.claude_code._find_claude_cli", return_value="/usr/bin/claude"):
            with patch("modules.pc_control.claude_code.asyncio.create_subprocess_exec", return_value=mock_proc):
                with patch("os.path.isdir", return_value=True):
                    result = await module.run(prompt="hello")
        assert "output" in result


# ---------------------------------------------------------------------------
# ProjectNotesReadModule
# ---------------------------------------------------------------------------


class TestProjectNotesReadModule:
    @pytest.fixture
    def module(self, tmp_path):
        return ProjectNotesReadModule(projects=SAMPLE_PROJECTS, notes_dir=str(tmp_path))

    @pytest.mark.asyncio
    async def test_contract(self, module):
        assert module.name == "pc_read_notes"
        assert "project" in module.parameters["required"]

    @pytest.mark.asyncio
    async def test_read_existing_notes(self, module, tmp_path):
        notes_file = tmp_path / "nova.md"
        notes_file.write_text("# TODO\n- Fix bug\n- Add feature\n")
        result = await module.run(project="nova")
        assert "Fix bug" in result
        assert "Add feature" in result

    @pytest.mark.asyncio
    async def test_read_nonexistent_notes(self, module):
        result = await module.run(project="nova")
        assert "No notes found" in result

    @pytest.mark.asyncio
    async def test_unknown_project(self, module):
        result = await module.run(project="nonexistent")
        assert "unknown project" in result.lower()

    @pytest.mark.asyncio
    async def test_empty_project_name(self, module):
        result = await module.run(project="")
        assert "required" in result.lower()


# ---------------------------------------------------------------------------
# ProjectNotesWriteModule
# ---------------------------------------------------------------------------


class TestProjectNotesWriteModule:
    @pytest.fixture
    def module(self, tmp_path):
        return ProjectNotesWriteModule(projects=SAMPLE_PROJECTS, notes_dir=str(tmp_path))

    @pytest.mark.asyncio
    async def test_contract(self, module):
        assert module.name == "pc_write_notes"
        assert "project" in module.parameters["required"]
        assert "content" in module.parameters["required"]

    @pytest.mark.asyncio
    async def test_write_new_notes(self, module, tmp_path):
        result = await module.run(project="nova", content="# My Notes\nHello")
        assert "Wrote" in result
        notes_file = tmp_path / "nova.md"
        assert notes_file.exists()
        assert notes_file.read_text() == "# My Notes\nHello"

    @pytest.mark.asyncio
    async def test_append_notes(self, module, tmp_path):
        notes_file = tmp_path / "nova.md"
        notes_file.write_text("Line 1\n")
        result = await module.run(project="nova", content="Line 2\n", mode="append")
        assert "Appended" in result
        assert notes_file.read_text() == "Line 1\nLine 2\n"

    @pytest.mark.asyncio
    async def test_unknown_project(self, module):
        result = await module.run(project="nonexistent", content="hello")
        assert "unknown project" in result.lower()

    @pytest.mark.asyncio
    async def test_empty_content(self, module):
        result = await module.run(project="nova", content="")
        assert "empty" in result.lower()

    @pytest.mark.asyncio
    async def test_invalid_mode(self, module):
        result = await module.run(project="nova", content="hello", mode="delete")
        assert "invalid mode" in result.lower()

    @pytest.mark.asyncio
    async def test_creates_directory(self, tmp_path):
        nested_dir = str(tmp_path / "nested" / "notes")
        module = ProjectNotesWriteModule(projects=SAMPLE_PROJECTS, notes_dir=nested_dir)
        result = await module.run(project="nova", content="hello")
        assert "Wrote" in result
        assert os.path.isfile(os.path.join(nested_dir, "nova.md"))
