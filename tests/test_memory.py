"""
Tests for core/memory.py

Uses a temporary SQLite file so the real data/memory.db is never touched.
"""

import pytest
import pytest_asyncio
import tempfile
import os

from core.memory import Memory


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def memory(tmp_path):
    """Return an initialised Memory instance backed by a temp DB."""
    db_path = str(tmp_path / "test_memory.db")
    mem = Memory(db_path=db_path)
    await mem.init()
    return mem


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_and_retrieve_message(memory):
    """Messages added to a session can be retrieved in order."""
    await memory.add_message("s1", "user", "Hello Nova")
    await memory.add_message("s1", "assistant", "Hello! How can I help?")

    ctx = await memory.get_context("s1")
    assert len(ctx) == 2
    assert ctx[0] == {"role": "user", "content": "Hello Nova"}
    assert ctx[1] == {"role": "assistant", "content": "Hello! How can I help?"}


@pytest.mark.asyncio
async def test_get_context_respects_max_messages(memory):
    """get_context returns at most max_messages entries (oldest dropped)."""
    for i in range(10):
        await memory.add_message("s2", "user", f"msg {i}")

    ctx = await memory.get_context("s2", max_messages=5)
    assert len(ctx) == 5
    # Should be the 5 most recent messages (msg 5 .. msg 9)
    contents = [m["content"] for m in ctx]
    assert contents == ["msg 5", "msg 6", "msg 7", "msg 8", "msg 9"]


@pytest.mark.asyncio
async def test_session_isolation(memory):
    """Messages from different sessions are independent."""
    await memory.add_message("session_a", "user", "Hello from A")
    await memory.add_message("session_b", "user", "Hello from B")

    ctx_a = await memory.get_context("session_a")
    ctx_b = await memory.get_context("session_b")

    assert len(ctx_a) == 1
    assert ctx_a[0]["content"] == "Hello from A"

    assert len(ctx_b) == 1
    assert ctx_b[0]["content"] == "Hello from B"


@pytest.mark.asyncio
async def test_empty_session_returns_empty_list(memory):
    """get_context on an unknown session returns an empty list."""
    ctx = await memory.get_context("nonexistent_session")
    assert ctx == []


@pytest.mark.asyncio
async def test_clear_session(memory):
    """clear_session removes all messages for that session only."""
    await memory.add_message("to_clear", "user", "will be deleted")
    await memory.add_message("to_keep", "user", "will stay")

    await memory.clear_session("to_clear")

    assert await memory.get_context("to_clear") == []
    assert len(await memory.get_context("to_keep")) == 1


@pytest.mark.asyncio
async def test_db_created_if_not_exists(tmp_path):
    """Memory.init() creates the DB file and parent dirs if missing."""
    nested_path = str(tmp_path / "deep" / "nested" / "memory.db")
    mem = Memory(db_path=nested_path)
    await mem.init()

    assert os.path.exists(nested_path)


@pytest.mark.asyncio
async def test_tool_message_stored_with_tool_name(memory):
    """Tool messages are stored in the DB (but filtered from get_context)."""
    await memory.add_message("s3", "tool", "Echo: hello", tool_name="echo")

    # get_context intentionally filters tool messages for LLM context building
    ctx = await memory.get_context("s3")
    assert len(ctx) == 0

    # Verify the message was actually persisted via direct DB query
    import aiosqlite
    async with aiosqlite.connect(memory.db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT role, content, tool_name FROM messages WHERE session_id = ?",
            ("s3",),
        ) as cursor:
            rows = await cursor.fetchall()
    assert len(rows) == 1
    assert rows[0]["role"] == "tool"
    assert rows[0]["content"] == "Echo: hello"
    assert rows[0]["tool_name"] == "echo"
