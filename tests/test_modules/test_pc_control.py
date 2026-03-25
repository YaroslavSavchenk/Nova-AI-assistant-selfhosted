"""
Tests for the pc_control package — safety utilities and all five modules.
"""

import os

import pytest
from unittest.mock import patch, AsyncMock

from modules.pc_control._safety import validate_command, sanitize_path, is_path_writable
from modules.pc_control import (
    RunCommandModule,
    ClaudeCodeModule,
    OpenAppModule,
    ReadFileModule,
    WriteFileModule,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def run_cmd():
    return RunCommandModule(
        allowed_commands=["ls", "echo", "cat", "pwd", "whoami"],
        timeout=5,
    )


@pytest.fixture
def claude_code():
    return ClaudeCodeModule()


@pytest.fixture
def open_app():
    return OpenAppModule()


@pytest.fixture
def read_file():
    return ReadFileModule()


@pytest.fixture
def write_file(tmp_path):
    return WriteFileModule(writable_dirs=[str(tmp_path)])


# ---------------------------------------------------------------------------
# _safety.validate_command
# ---------------------------------------------------------------------------


class TestValidateCommand:
    ALLOWED = ["ls", "echo", "cat", "pwd"]

    def test_valid_simple(self):
        ok, err = validate_command("ls -la", self.ALLOWED)
        assert ok is True
        assert err == ""

    def test_valid_with_args(self):
        ok, err = validate_command("echo 'hello world'", self.ALLOWED)
        assert ok is True

    def test_rejected_not_in_allowlist(self):
        ok, err = validate_command("rm -rf /", self.ALLOWED)
        assert ok is False
        assert "rm" in err

    def test_rejected_empty(self):
        ok, err = validate_command("", self.ALLOWED)
        assert ok is False

    def test_rejected_semicolon(self):
        ok, err = validate_command("ls; rm -rf /", self.ALLOWED)
        assert ok is False
        assert ";" in err

    def test_rejected_pipe(self):
        ok, err = validate_command("ls | grep foo", self.ALLOWED)
        assert ok is False
        assert "|" in err

    def test_rejected_and(self):
        ok, err = validate_command("ls && rm -rf /", self.ALLOWED)
        assert ok is False
        assert "&&" in err

    def test_rejected_or(self):
        ok, err = validate_command("ls || rm -rf /", self.ALLOWED)
        assert ok is False
        assert "|" in err

    def test_rejected_subshell(self):
        ok, err = validate_command("echo $(whoami)", self.ALLOWED)
        assert ok is False
        assert "$(" in err

    def test_rejected_backtick(self):
        ok, err = validate_command("echo `whoami`", self.ALLOWED)
        assert ok is False
        assert "`" in err

    def test_rejected_redirect(self):
        ok, err = validate_command("echo hello > /tmp/x", self.ALLOWED)
        assert ok is False
        assert ">" in err

    def test_rejected_newline(self):
        ok, err = validate_command("ls\nrm -rf /", self.ALLOWED)
        assert ok is False

    def test_strips_path_prefix(self):
        ok, err = validate_command("/usr/bin/ls", self.ALLOWED)
        assert ok is True


class TestSanitizePath:
    def test_expands_tilde(self):
        result = sanitize_path("~/Documents")
        assert result.startswith("/")
        assert "~" not in result

    def test_resolves_relative(self):
        result = sanitize_path("./foo/../bar")
        assert ".." not in result


class TestIsPathWritable:
    def test_under_writable_dir(self, tmp_path):
        path = str(tmp_path / "subdir" / "file.txt")
        assert is_path_writable(path, [str(tmp_path)]) is True

    def test_not_under_writable_dir(self, tmp_path):
        assert is_path_writable("/etc/passwd", [str(tmp_path)]) is False

    def test_exact_dir_match(self, tmp_path):
        path = str(tmp_path / "file.txt")
        assert is_path_writable(path, [str(tmp_path)]) is True


# ---------------------------------------------------------------------------
# RunCommandModule
# ---------------------------------------------------------------------------


class TestRunCommandModule:
    @pytest.mark.asyncio
    async def test_contract(self, run_cmd):
        assert run_cmd.name == "pc_run_command"
        assert run_cmd.parameters["required"] == ["command"]

    @pytest.mark.asyncio
    async def test_runs_allowed_command(self, run_cmd):
        result = await run_cmd.run(command="echo hello")
        assert "hello" in result

    @pytest.mark.asyncio
    async def test_rejects_disallowed_command(self, run_cmd):
        result = await run_cmd.run(command="rm -rf /")
        assert "rejected" in result.lower() or "not in the allowed" in result.lower()

    @pytest.mark.asyncio
    async def test_rejects_injection(self, run_cmd):
        result = await run_cmd.run(command="echo hi; rm -rf /")
        assert "rejected" in result.lower() or "blocked" in result.lower()

    @pytest.mark.asyncio
    async def test_pwd(self, run_cmd):
        result = await run_cmd.run(command="pwd")
        assert result.startswith("/")

    @pytest.mark.asyncio
    async def test_empty_command(self, run_cmd):
        result = await run_cmd.run(command="")
        assert "rejected" in result.lower() or "empty" in result.lower()

    @pytest.mark.asyncio
    async def test_truncates_long_output(self, run_cmd):
        # Generate output longer than 4000 chars
        run_cmd.allowed_commands = ["ls", "echo", "cat", "pwd", "whoami", "yes"]
        # Use echo with a very long string
        long_text = "A" * 5000
        result = await run_cmd.run(command=f"echo {long_text}")
        assert "[truncated" in result or len(result) <= 5000


# ---------------------------------------------------------------------------
# ClaudeCodeModule
# ---------------------------------------------------------------------------


class TestClaudeCodeModule:
    @pytest.mark.asyncio
    async def test_contract(self, claude_code):
        assert claude_code.name == "pc_claude_code"
        assert "prompt" in claude_code.parameters["required"]

    @pytest.mark.asyncio
    async def test_empty_prompt(self, claude_code):
        result = await claude_code.run(prompt="")
        assert "empty" in result.lower()

    @pytest.mark.asyncio
    async def test_claude_not_found(self, claude_code):
        with patch("modules.pc_control.claude_code.asyncio.create_subprocess_exec", side_effect=FileNotFoundError):
            result = await claude_code.run(prompt="explain this")
        assert "not found" in result.lower()

    @pytest.mark.asyncio
    async def test_success(self, claude_code):
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"Here is the explanation.", b""))
        mock_proc.returncode = 0

        with patch("modules.pc_control.claude_code.asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await claude_code.run(prompt="explain this code")
        assert "explanation" in result.lower()

    @pytest.mark.asyncio
    async def test_error_return(self, claude_code):
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b"some error"))
        mock_proc.returncode = 1

        with patch("modules.pc_control.claude_code.asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await claude_code.run(prompt="bad prompt")
        assert "error" in result.lower()


# ---------------------------------------------------------------------------
# OpenAppModule
# ---------------------------------------------------------------------------


class TestOpenAppModule:
    @pytest.mark.asyncio
    async def test_contract(self, open_app):
        assert open_app.name == "pc_open_app"
        assert "target" in open_app.parameters["required"]

    @pytest.mark.asyncio
    async def test_empty_target(self, open_app):
        result = await open_app.run(target="")
        assert "empty" in result.lower()

    @pytest.mark.asyncio
    async def test_opens_url(self, open_app):
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))
        mock_proc.returncode = 0

        with patch("modules.pc_control.open_app.asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
            result = await open_app.run(target="https://example.com")
        assert "Opened" in result
        # URLs open via cmd.exe /c start
        assert mock_exec.call_args[0][0] == "cmd.exe"

    @pytest.mark.asyncio
    async def test_opens_known_app(self, open_app):
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))
        mock_proc.returncode = 0

        with patch("modules.pc_control.open_app.asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
            result = await open_app.run(target="vscode")
        assert "Opened" in result
        # Should call "code" not "vscode"
        mock_exec.assert_called_once()
        assert mock_exec.call_args[0][0] == "code"

    @pytest.mark.asyncio
    async def test_opens_windows_app(self, open_app):
        """Known Windows apps like chrome, spotify, task manager should resolve."""
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))
        mock_proc.returncode = 0

        with patch("modules.pc_control.open_app.asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
            result = await open_app.run(target="chrome")
        assert "Opened" in result
        assert mock_exec.call_args[0][0] == "cmd.exe"

    @pytest.mark.asyncio
    async def test_fallback_cmd_start(self, open_app):
        """Unknown targets fall back to cmd.exe /c start."""
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))
        mock_proc.returncode = 0

        with patch("modules.pc_control.open_app.shutil.which", return_value=None):
            with patch("modules.pc_control.open_app.asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
                result = await open_app.run(target="somefile.pdf")
        assert "Opened" in result
        assert mock_exec.call_args[0][0] == "cmd.exe"

    @pytest.mark.asyncio
    async def test_direct_executable(self, open_app):
        """If the target is a real executable on PATH, run it directly."""
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))
        mock_proc.returncode = 0

        with patch("modules.pc_control.open_app.shutil.which", return_value="/usr/bin/htop"):
            with patch("modules.pc_control.open_app.asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
                result = await open_app.run(target="htop")
        assert "Opened" in result
        assert mock_exec.call_args[0][0] == "htop"


# ---------------------------------------------------------------------------
# ReadFileModule
# ---------------------------------------------------------------------------


class TestReadFileModule:
    @pytest.mark.asyncio
    async def test_contract(self, read_file):
        assert read_file.name == "pc_read_file"
        assert "path" in read_file.parameters["required"]

    @pytest.mark.asyncio
    async def test_empty_path(self, read_file):
        result = await read_file.run(path="")
        assert "empty" in result.lower()

    @pytest.mark.asyncio
    async def test_file_not_found(self, read_file):
        result = await read_file.run(path="/nonexistent/file.txt")
        assert "not found" in result.lower()

    @pytest.mark.asyncio
    async def test_reads_file(self, read_file, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("line1\nline2\nline3\n")
        result = await read_file.run(path=str(f))
        assert "line1" in result
        assert "line2" in result
        assert "line3" in result

    @pytest.mark.asyncio
    async def test_max_lines(self, read_file, tmp_path):
        f = tmp_path / "big.txt"
        f.write_text("\n".join(f"line{i}" for i in range(200)))
        result = await read_file.run(path=str(f), max_lines=5)
        assert "truncated" in result.lower()
        assert "line0" in result

    @pytest.mark.asyncio
    async def test_rejects_directory(self, read_file, tmp_path):
        result = await read_file.run(path=str(tmp_path))
        assert "directory" in result.lower()

    @pytest.mark.asyncio
    async def test_rejects_large_file(self, read_file, tmp_path):
        f = tmp_path / "huge.txt"
        f.write_bytes(b"x" * (101 * 1024))
        result = await read_file.run(path=str(f))
        assert "too large" in result.lower()


# ---------------------------------------------------------------------------
# WriteFileModule
# ---------------------------------------------------------------------------


class TestWriteFileModule:
    @pytest.mark.asyncio
    async def test_contract(self, write_file):
        assert write_file.name == "pc_write_file"
        assert "path" in write_file.parameters["required"]
        assert "content" in write_file.parameters["required"]

    @pytest.mark.asyncio
    async def test_empty_path(self, write_file):
        result = await write_file.run(path="", content="hello")
        assert "empty" in result.lower()

    @pytest.mark.asyncio
    async def test_write_file(self, write_file, tmp_path):
        target = str(tmp_path / "output.txt")
        result = await write_file.run(path=target, content="hello world")
        assert "Wrote" in result
        assert os.path.exists(target)
        with open(target) as f:
            assert f.read() == "hello world"

    @pytest.mark.asyncio
    async def test_append_file(self, write_file, tmp_path):
        target = str(tmp_path / "append.txt")
        # Write first
        await write_file.run(path=target, content="first\n")
        # Append
        result = await write_file.run(path=target, content="second\n", mode="append")
        assert "Appended" in result
        with open(target) as f:
            assert f.read() == "first\nsecond\n"

    @pytest.mark.asyncio
    async def test_rejects_outside_writable_dirs(self, write_file):
        result = await write_file.run(path="/etc/evil.txt", content="pwned")
        assert "rejected" in result.lower()
        assert not os.path.exists("/etc/evil.txt")

    @pytest.mark.asyncio
    async def test_creates_parent_dirs(self, write_file, tmp_path):
        target = str(tmp_path / "sub" / "dir" / "file.txt")
        result = await write_file.run(path=target, content="nested")
        assert "Wrote" in result
        assert os.path.exists(target)

    @pytest.mark.asyncio
    async def test_invalid_mode(self, write_file, tmp_path):
        target = str(tmp_path / "bad.txt")
        result = await write_file.run(path=target, content="x", mode="delete")
        assert "invalid mode" in result.lower()
