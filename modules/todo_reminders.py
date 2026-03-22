"""
Todo & Reminders module for Nova — persistent todo list backed by SQLite.
"""

import logging

import aiosqlite

from modules.base import NovaModule

logger = logging.getLogger(__name__)

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS todos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    done INTEGER NOT NULL DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""


class TodoModule(NovaModule):
    """Manage a persistent todo list stored in SQLite."""

    name: str = "todo"
    description: str = (
        "Manage a persistent todo list. Can create todos, list them, mark as "
        "complete, and delete them."
    )
    parameters: dict = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["add", "list", "complete", "delete"],
                "description": "Action to perform",
            },
            "text": {
                "type": "string",
                "description": "Todo text (required for add)",
            },
            "id": {
                "type": "integer",
                "description": "Todo ID (required for complete and delete)",
            },
        },
        "required": ["action"],
    }

    def __init__(self, db_path: str = "data/memory.db") -> None:
        self._db_path = db_path

    async def init(self) -> None:
        """Create the todos table if it does not already exist."""
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(_CREATE_TABLE)
            await db.commit()

    # ------------------------------------------------------------------
    # run()
    # ------------------------------------------------------------------

    async def run(self, **kwargs) -> str:
        try:
            action: str = kwargs.get("action", "").lower()

            if action == "add":
                return await self._add(kwargs.get("text", ""))
            if action == "list":
                return await self._list()
            if action == "complete":
                return await self._complete(kwargs.get("id"))
            if action == "delete":
                return await self._delete(kwargs.get("id"))

            return f"Unknown action: {action!r}. Valid actions: add, list, complete, delete."

        except Exception as exc:
            logger.exception("TodoModule error")
            return f"Todo operation failed: {exc}"

    # ------------------------------------------------------------------
    # Private action helpers
    # ------------------------------------------------------------------

    async def _add(self, text: str) -> str:
        text = (text or "").strip()
        if not text:
            return "Error: todo text cannot be empty."
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "INSERT INTO todos (text) VALUES (?)", (text,)
            )
            await db.commit()
            todo_id = cursor.lastrowid
        return f"Added todo #{todo_id}: {text}"

    async def _list(self) -> str:
        async with aiosqlite.connect(self._db_path) as db:
            async with db.execute(
                "SELECT id, text, done FROM todos ORDER BY id ASC"
            ) as cursor:
                rows = await cursor.fetchall()

        if not rows:
            return "No todos yet."

        lines = []
        for row_id, text, done in rows:
            marker = "✓" if done else "○"
            lines.append(f"{marker} #{row_id}: {text}")
        return "\n".join(lines)

    async def _complete(self, todo_id) -> str:
        if todo_id is None:
            return "Error: id is required for complete action."
        todo_id = int(todo_id)
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "UPDATE todos SET done = 1 WHERE id = ?", (todo_id,)
            )
            await db.commit()
            if cursor.rowcount == 0:
                return f"Todo #{todo_id} not found."
        return f"Marked #{todo_id} as done."

    async def _delete(self, todo_id) -> str:
        if todo_id is None:
            return "Error: id is required for delete action."
        todo_id = int(todo_id)
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "DELETE FROM todos WHERE id = ?", (todo_id,)
            )
            await db.commit()
            if cursor.rowcount == 0:
                return f"Todo #{todo_id} not found."
        return f"Deleted todo #{todo_id}."
