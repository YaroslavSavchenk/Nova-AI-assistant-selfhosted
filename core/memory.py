"""
SQLite-backed memory for Nova conversations.

Uses aiosqlite for fully async DB access.
Only this module is allowed to read/write data/memory.db.
"""

import logging
from pathlib import Path

import aiosqlite

logger = logging.getLogger(__name__)

_CREATE_MESSAGES_TABLE = """
CREATE TABLE IF NOT EXISTS messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT    NOT NULL,
    role        TEXT    NOT NULL,
    content     TEXT    NOT NULL,
    tool_name   TEXT,
    timestamp   DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""


class Memory:
    """Async SQLite-backed conversation memory."""

    def __init__(self, db_path: str = "data/memory.db"):
        self.db_path = db_path

    async def init(self) -> None:
        """
        Create the database file and tables if they do not exist.
        Also creates the parent directory if needed.
        """
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(_CREATE_MESSAGES_TABLE)
            await db.commit()
        logger.debug("Memory DB initialised at %s", self.db_path)

    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        tool_name: str | None = None,
    ) -> None:
        """
        Persist a message to the DB.

        Args:
            session_id: Conversation session identifier.
            role: One of 'user', 'assistant', 'tool', 'system'.
            content: Message text.
            tool_name: Populated when role='tool'.
        """
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO messages (session_id, role, content, tool_name) "
                "VALUES (?, ?, ?, ?)",
                (session_id, role, content, tool_name),
            )
            await db.commit()

    async def get_context(
        self,
        session_id: str,
        max_messages: int = 20,
    ) -> list[dict]:
        """
        Retrieve the most recent messages for a session, oldest first.

        Args:
            session_id: Conversation session identifier.
            max_messages: Maximum number of messages to return.

        Returns:
            List of dicts with 'role' and 'content' keys.
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT role, content FROM (
                    SELECT id, role, content, timestamp
                    FROM messages
                    WHERE session_id = ?
                    ORDER BY id DESC
                    LIMIT ?
                ) ORDER BY id ASC
                """,
                (session_id, max_messages),
            ) as cursor:
                rows = await cursor.fetchall()

        return [{"role": row["role"], "content": row["content"]} for row in rows]

    async def clear_session(self, session_id: str) -> None:
        """Delete all messages for the given session."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "DELETE FROM messages WHERE session_id = ?", (session_id,)
            )
            await db.commit()
        logger.debug("Cleared session %s", session_id)
