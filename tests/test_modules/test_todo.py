"""
Tests for modules/todo_reminders.py
"""

import pytest
import pytest_asyncio

from modules.todo_reminders import TodoModule


@pytest_asyncio.fixture
async def todo(tmp_path):
    db_path = str(tmp_path / "test_todos.db")
    module = TodoModule(db_path=db_path)
    await module.init()
    return module


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_then_list_shows_item(todo):
    """Adding a todo and then listing it returns the item in the output."""
    add_result = await todo.run(action="add", text="Buy milk")
    assert "Buy milk" in add_result
    assert "#" in add_result

    list_result = await todo.run(action="list")
    assert "Buy milk" in list_result
    assert "○" in list_result  # not done


@pytest.mark.asyncio
async def test_complete_marks_todo_done(todo):
    """Completing a todo by ID marks it with the done marker."""
    await todo.run(action="add", text="Write tests")
    # Extract the ID from the add result
    add_result = await todo.run(action="add", text="Write docs")
    todo_id = int(add_result.split("#")[1].split(":")[0])

    complete_result = await todo.run(action="complete", id=todo_id)
    assert f"#{todo_id}" in complete_result
    assert "done" in complete_result.lower()

    list_result = await todo.run(action="list")
    assert "✓" in list_result


@pytest.mark.asyncio
async def test_delete_removes_todo(todo):
    """Deleting a todo by ID removes it from the list."""
    add_result = await todo.run(action="add", text="Clean desk")
    todo_id = int(add_result.split("#")[1].split(":")[0])

    delete_result = await todo.run(action="delete", id=todo_id)
    assert f"#{todo_id}" in delete_result
    assert "Deleted" in delete_result

    list_result = await todo.run(action="list")
    assert "Clean desk" not in list_result


@pytest.mark.asyncio
async def test_complete_invalid_id_returns_not_found(todo):
    """Completing a non-existent ID returns 'not found' string, not an exception."""
    result = await todo.run(action="complete", id=9999)
    assert "not found" in result.lower()
    assert "9999" in result


@pytest.mark.asyncio
async def test_delete_invalid_id_returns_not_found(todo):
    """Deleting a non-existent ID returns 'not found' string, not an exception."""
    result = await todo.run(action="delete", id=9999)
    assert "not found" in result.lower()
    assert "9999" in result


@pytest.mark.asyncio
async def test_list_empty_db_returns_friendly_message(todo):
    """Listing with no todos returns 'No todos yet.' message."""
    result = await todo.run(action="list")
    assert result == "No todos yet."


@pytest.mark.asyncio
async def test_add_multiple_todos_all_appear_in_list(todo):
    """Multiple added todos all show up in the list."""
    await todo.run(action="add", text="Task A")
    await todo.run(action="add", text="Task B")
    await todo.run(action="add", text="Task C")

    result = await todo.run(action="list")
    assert "Task A" in result
    assert "Task B" in result
    assert "Task C" in result


@pytest.mark.asyncio
async def test_complete_does_not_delete_todo(todo):
    """Completing a todo keeps it in the list with a done marker."""
    add_result = await todo.run(action="add", text="Read book")
    todo_id = int(add_result.split("#")[1].split(":")[0])

    await todo.run(action="complete", id=todo_id)
    list_result = await todo.run(action="list")

    assert "Read book" in list_result
    assert "✓" in list_result


@pytest.mark.asyncio
async def test_add_empty_text_returns_error(todo):
    """Adding a todo with empty text returns an error string."""
    result = await todo.run(action="add", text="")
    assert "empty" in result.lower() or "error" in result.lower()


@pytest.mark.asyncio
async def test_unknown_action_returns_error(todo):
    """An unknown action returns a descriptive error string, not an exception."""
    result = await todo.run(action="fly")
    assert "Unknown action" in result or "fly" in result
