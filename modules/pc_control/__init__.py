"""PC control package — shell commands, app launching, file I/O, Claude Code, and projects."""

from modules.pc_control.run_command import RunCommandModule
from modules.pc_control.claude_code import ClaudeCodeModule
from modules.pc_control.open_app import OpenAppModule
from modules.pc_control.read_file import ReadFileModule
from modules.pc_control.write_file import WriteFileModule
from modules.pc_control.projects import ListProjectsModule
from modules.pc_control.notes import ProjectNotesReadModule, ProjectNotesWriteModule

__all__ = [
    "RunCommandModule",
    "ClaudeCodeModule",
    "OpenAppModule",
    "ReadFileModule",
    "WriteFileModule",
    "ListProjectsModule",
    "ProjectNotesReadModule",
    "ProjectNotesWriteModule",
]
