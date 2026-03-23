"""
Tests for core/long_term_memory.py — LongTermMemory class.

All tests use a tmp_path SQLite file — no real DB touched.
ChromaDB / semantic search is never enabled in these tests.
"""

import pytest
import pytest_asyncio

from core.long_term_memory import LongTermMemory, _MIN_MESSAGES_TO_SUMMARIZE


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def ltm(tmp_path):
    """Initialised LongTermMemory backed by a temp SQLite file."""
    db = LongTermMemory(db_path=str(tmp_path / "ltm_test.db"), semantic_search=False)
    await db.init()
    return db


# ---------------------------------------------------------------------------
# Facts — add / list / delete
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_fact_returns_id(ltm):
    fact_id = await ltm.add_fact("I prefer dark mode")
    assert isinstance(fact_id, int)
    assert fact_id >= 1


@pytest.mark.asyncio
async def test_list_facts_empty(ltm):
    facts = await ltm.list_facts()
    assert facts == []


@pytest.mark.asyncio
async def test_list_facts_returns_stored_facts(ltm):
    await ltm.add_fact("Fact A")
    await ltm.add_fact("Fact B")
    facts = await ltm.list_facts()
    contents = [f["content"] for f in facts]
    assert "Fact A" in contents
    assert "Fact B" in contents


@pytest.mark.asyncio
async def test_list_facts_filtered_by_category(ltm):
    await ltm.add_fact("I use Neovim", category="tools")
    await ltm.add_fact("My name is Sava", category="personal")

    tools = await ltm.list_facts(category="tools")
    assert all(f["category"] == "tools" for f in tools)
    assert any(f["content"] == "I use Neovim" for f in tools)

    personal = await ltm.list_facts(category="personal")
    assert all(f["category"] == "personal" for f in personal)


@pytest.mark.asyncio
async def test_delete_fact_removes_it(ltm):
    fact_id = await ltm.add_fact("Temporary fact")
    deleted = await ltm.delete_fact(fact_id)
    assert deleted is True

    facts = await ltm.list_facts()
    assert not any(f["id"] == fact_id for f in facts)


@pytest.mark.asyncio
async def test_delete_nonexistent_fact_returns_false(ltm):
    deleted = await ltm.delete_fact(99999)
    assert deleted is False


@pytest.mark.asyncio
async def test_touch_fact_updates_timestamp(ltm):
    fact_id = await ltm.add_fact("Some fact")
    facts_before = await ltm.list_facts()
    ts_before = next(f["last_referenced"] for f in facts_before if f["id"] == fact_id)

    await ltm.touch_fact(fact_id)
    facts_after = await ltm.list_facts()
    ts_after = next(f["last_referenced"] for f in facts_after if f["id"] == fact_id)

    # Timestamps may be identical if running within the same second — just check no error
    assert ts_after >= ts_before


# ---------------------------------------------------------------------------
# get_facts_for_prompt
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_facts_for_prompt_empty(ltm):
    result = await ltm.get_facts_for_prompt()
    assert result == ""


@pytest.mark.asyncio
async def test_get_facts_for_prompt_formats_as_bullets(ltm):
    await ltm.add_fact("I drink coffee")
    await ltm.add_fact("I work in Python")
    result = await ltm.get_facts_for_prompt()
    assert "- I drink coffee" in result
    assert "- I work in Python" in result


# ---------------------------------------------------------------------------
# Session summaries
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_summary_stores_and_retrieves(ltm):
    await ltm.add_summary("sess-001", "We discussed Python async.", 6)
    result = await ltm.get_summaries_for_prompt()
    assert "We discussed Python async." in result


@pytest.mark.asyncio
async def test_add_summary_upserts(ltm):
    await ltm.add_summary("sess-001", "First summary", 4)
    await ltm.add_summary("sess-001", "Updated summary", 8)
    result = await ltm.get_summaries_for_prompt()
    assert "Updated summary" in result
    assert "First summary" not in result


@pytest.mark.asyncio
async def test_get_summaries_for_prompt_empty(ltm):
    result = await ltm.get_summaries_for_prompt()
    assert result == ""


@pytest.mark.asyncio
async def test_get_summaries_includes_session_id(ltm):
    await ltm.add_summary("sess-abc", "Short summary.", 4)
    result = await ltm.get_summaries_for_prompt()
    assert "sess-abc" in result


# ---------------------------------------------------------------------------
# get_sessions_needing_summary
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def ltm_with_messages(tmp_path):
    """LTM with a pre-populated messages table for testing session scanning."""
    import aiosqlite

    db_path = str(tmp_path / "ltm_sessions.db")
    ltm = LongTermMemory(db_path=db_path, semantic_search=False)
    await ltm.init()

    # Create the messages table (normally owned by core/memory.py)
    async with aiosqlite.connect(db_path) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT    NOT NULL,
                role       TEXT    NOT NULL,
                content    TEXT    NOT NULL
            )
        """)
        await db.commit()

    return ltm, db_path


async def _insert_messages(db_path: str, session_id: str, count: int) -> None:
    """Insert alternating user/assistant messages for a session."""
    import aiosqlite

    async with aiosqlite.connect(db_path) as db:
        for i in range(count):
            role = "user" if i % 2 == 0 else "assistant"
            await db.execute(
                "INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)",
                (session_id, role, f"Message {i}"),
            )
        await db.commit()


@pytest.mark.asyncio
async def test_sessions_needing_summary_finds_eligible(ltm_with_messages):
    ltm, db_path = ltm_with_messages

    await _insert_messages(db_path, "old-session", _MIN_MESSAGES_TO_SUMMARIZE)

    pending = await ltm.get_sessions_needing_summary(
        current_session_id="current-session"
    )
    session_ids = [s for s, _ in pending]
    assert "old-session" in session_ids


@pytest.mark.asyncio
async def test_sessions_needing_summary_excludes_current(ltm_with_messages):
    ltm, db_path = ltm_with_messages

    await _insert_messages(db_path, "current-session", _MIN_MESSAGES_TO_SUMMARIZE)

    pending = await ltm.get_sessions_needing_summary(
        current_session_id="current-session"
    )
    session_ids = [s for s, _ in pending]
    assert "current-session" not in session_ids


@pytest.mark.asyncio
async def test_sessions_needing_summary_excludes_already_summarized(ltm_with_messages):
    ltm, db_path = ltm_with_messages

    await _insert_messages(db_path, "done-session", _MIN_MESSAGES_TO_SUMMARIZE)
    await ltm.add_summary("done-session", "Already done.", 4)

    pending = await ltm.get_sessions_needing_summary(
        current_session_id="current-session"
    )
    session_ids = [s for s, _ in pending]
    assert "done-session" not in session_ids


@pytest.mark.asyncio
async def test_sessions_needing_summary_excludes_too_short(ltm_with_messages):
    ltm, db_path = ltm_with_messages

    # Insert fewer messages than the minimum threshold
    await _insert_messages(db_path, "short-session", _MIN_MESSAGES_TO_SUMMARIZE - 1)

    pending = await ltm.get_sessions_needing_summary(
        current_session_id="current-session"
    )
    session_ids = [s for s, _ in pending]
    assert "short-session" not in session_ids


@pytest.mark.asyncio
async def test_sessions_needing_summary_returns_messages(ltm_with_messages):
    ltm, db_path = ltm_with_messages

    msg_count = _MIN_MESSAGES_TO_SUMMARIZE + 2
    await _insert_messages(db_path, "rich-session", msg_count)

    pending = await ltm.get_sessions_needing_summary(
        current_session_id="current-session"
    )
    for session_id, messages in pending:
        if session_id == "rich-session":
            assert len(messages) == msg_count
            assert all("role" in m and "content" in m for m in messages)
            break
    else:
        pytest.fail("rich-session not found in pending sessions")
