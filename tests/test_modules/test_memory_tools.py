"""
Tests for modules/memory — RememberFactModule, RecallFactsModule, ForgetFactModule.

Each test gets a fresh LongTermMemory instance backed by a tmp_path SQLite DB so
tests are fully isolated and never touch data/memory.db.
"""

import pytest
import pytest_asyncio

from core.long_term_memory import LongTermMemory
from modules.memory.remember import RememberFactModule
from modules.memory.recall import RecallFactsModule
from modules.memory.forget import ForgetFactModule


# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def ltm(tmp_path):
    """Initialised LongTermMemory backed by a temporary SQLite file."""
    db_path = str(tmp_path / "test_memory.db")
    memory = LongTermMemory(db_path=db_path, semantic_search=False)
    await memory.init()
    return memory


@pytest_asyncio.fixture
async def remember(ltm):
    return RememberFactModule(ltm=ltm)


@pytest_asyncio.fixture
async def recall(ltm):
    return RecallFactsModule(ltm=ltm)


@pytest_asyncio.fixture
async def forget(ltm):
    return ForgetFactModule(ltm=ltm)


# ---------------------------------------------------------------------------
# Helper to get all three modules sharing the same LTM instance
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def memory_tools(tmp_path):
    """All three modules sharing one LongTermMemory — needed for integration tests."""
    db_path = str(tmp_path / "test_memory_shared.db")
    memory = LongTermMemory(db_path=db_path, semantic_search=False)
    await memory.init()
    return (
        RememberFactModule(ltm=memory),
        RecallFactsModule(ltm=memory),
        ForgetFactModule(ltm=memory),
    )


# ---------------------------------------------------------------------------
# RememberFactModule tests
# ---------------------------------------------------------------------------


def _extract_remember_id(result: str) -> int:
    """Parse the fact ID from 'Remembered (#N): ...' format."""
    # result looks like: "Remembered (#1): Some fact"
    id_str = result.split("(#")[1].split(")")[0].strip()
    return int(id_str)


@pytest.mark.asyncio
async def test_remember_stores_fact_and_returns_id(remember):
    """run() with a content string should return the content and an ID like #N."""
    result = await remember.run(content="My name is Sava")
    assert "My name is Sava" in result
    assert "#" in result
    # ID portion must be a digit
    fact_id = _extract_remember_id(result)
    assert fact_id >= 1


@pytest.mark.asyncio
async def test_remember_empty_content_returns_error(remember):
    """run() with an empty content string must return an error, not raise."""
    result = await remember.run(content="")
    assert "error" in result.lower() or "empty" in result.lower()


@pytest.mark.asyncio
async def test_remember_with_category(remember):
    """run() with a category kwarg should succeed and include the fact content."""
    result = await remember.run(content="I prefer dark mode", category="preference")
    assert "I prefer dark mode" in result
    # Must not be an error response
    assert "error" not in result.lower()
    assert "failed" not in result.lower()


@pytest.mark.asyncio
async def test_remember_whitespace_only_content_returns_error(remember):
    """run() where content is only whitespace should be treated as empty."""
    result = await remember.run(content="   ")
    assert "error" in result.lower() or "empty" in result.lower()


@pytest.mark.asyncio
async def test_remember_ids_are_unique_and_incrementing(remember):
    """Two successive remember calls should return different ascending IDs."""
    r1 = await remember.run(content="Fact one")
    r2 = await remember.run(content="Fact two")

    id1 = _extract_remember_id(r1)
    id2 = _extract_remember_id(r2)
    assert id2 > id1


# ---------------------------------------------------------------------------
# RecallFactsModule tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_recall_empty_returns_no_facts_message(recall):
    """recall with an empty DB should return a 'no facts' message, not an error."""
    result = await recall.run()
    assert "no facts" in result.lower()
    assert "error" not in result.lower()
    assert "failed" not in result.lower()


@pytest.mark.asyncio
async def test_recall_lists_stored_facts(memory_tools):
    """After storing two facts, recall should include both in the output."""
    remember, recall, _ = memory_tools

    await remember.run(content="I work as a software developer")
    await remember.run(content="My favourite editor is Neovim")

    result = await recall.run()
    assert "I work as a software developer" in result
    assert "My favourite editor is Neovim" in result


@pytest.mark.asyncio
async def test_recall_filter_by_category(memory_tools):
    """recall with category= should only return facts from that category."""
    remember, recall, _ = memory_tools

    await remember.run(content="I prefer dark mode", category="preference")
    await remember.run(content="My name is Sava", category="personal")

    pref_result = await recall.run(category="preference")
    assert "I prefer dark mode" in pref_result
    assert "My name is Sava" not in pref_result

    personal_result = await recall.run(category="personal")
    assert "My name is Sava" in personal_result
    assert "I prefer dark mode" not in personal_result


@pytest.mark.asyncio
async def test_recall_filter_by_nonexistent_category_returns_no_facts(memory_tools):
    """Filtering by a category that has no facts returns a 'no facts' message."""
    remember, recall, _ = memory_tools
    await remember.run(content="Some fact", category="personal")

    result = await recall.run(category="work")
    assert "no facts" in result.lower()


@pytest.mark.asyncio
async def test_recall_output_contains_fact_ids(memory_tools):
    """Recall output should expose fact IDs so the user can reference them."""
    remember, recall, _ = memory_tools
    await remember.run(content="Remember this")

    result = await recall.run()
    assert "#" in result


# ---------------------------------------------------------------------------
# ForgetFactModule tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_forget_removes_fact(memory_tools):
    """Remember a fact, forget it by ID, then recall confirms it is gone."""
    remember, recall, forget = memory_tools

    add_result = await remember.run(content="Temporary fact to delete")
    fact_id = _extract_remember_id(add_result)

    forget_result = await forget.run(fact_id=fact_id)
    assert str(fact_id) in forget_result
    assert "error" not in forget_result.lower()
    assert "failed" not in forget_result.lower()

    recall_result = await recall.run()
    assert "Temporary fact to delete" not in recall_result


@pytest.mark.asyncio
async def test_forget_nonexistent_id_returns_not_found(forget):
    """Forgetting an ID that was never stored should return a 'not found' message."""
    result = await forget.run(fact_id=99999)
    assert "not found" in result.lower() or "no fact" in result.lower()
    assert "99999" in result


@pytest.mark.asyncio
async def test_forget_missing_fact_id_returns_error(forget):
    """Calling forget without fact_id kwarg must return an error string, not raise."""
    result = await forget.run()
    assert "error" in result.lower() or "required" in result.lower()
    assert "fact_id" in result.lower()


@pytest.mark.asyncio
async def test_forget_only_deletes_targeted_fact(memory_tools):
    """Forgetting one fact must leave other facts intact."""
    remember, recall, forget = memory_tools

    r1 = await remember.run(content="Fact to keep")
    r2 = await remember.run(content="Fact to delete")

    id_to_delete = _extract_remember_id(r2)
    await forget.run(fact_id=id_to_delete)

    recall_result = await recall.run()
    assert "Fact to keep" in recall_result
    assert "Fact to delete" not in recall_result


@pytest.mark.asyncio
async def test_forget_same_id_twice_second_is_not_found(memory_tools):
    """Forgetting an already-deleted fact should return 'not found', not an error."""
    remember, _, forget = memory_tools

    add_result = await remember.run(content="One-time fact")
    fact_id = _extract_remember_id(add_result)

    await forget.run(fact_id=fact_id)
    second_result = await forget.run(fact_id=fact_id)

    assert "not found" in second_result.lower() or "no fact" in second_result.lower()
    assert "failed" not in second_result.lower()
