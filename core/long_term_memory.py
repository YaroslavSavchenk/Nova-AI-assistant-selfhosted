"""
Long-term memory for Nova — facts and session summaries.

Two layers:
  1. SQLite — facts the user has stored + session summaries (always available)
  2. ChromaDB — optional semantic search over summaries (requires chromadb +
     nomic-embed-text via Ollama). Falls back to recency-based retrieval if
     not available.

Only this module and core/memory.py are allowed to touch data/memory.db.
"""

import json
import logging
from pathlib import Path

import aiosqlite

logger = logging.getLogger(__name__)

_CREATE_FACTS_TABLE = """
CREATE TABLE IF NOT EXISTS facts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    content     TEXT    NOT NULL,
    category    TEXT    NOT NULL DEFAULT 'general',
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""

_CREATE_SUMMARIES_TABLE = """
CREATE TABLE IF NOT EXISTS session_summaries (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id    TEXT    NOT NULL UNIQUE,
    summary       TEXT    NOT NULL,
    message_count INTEGER NOT NULL DEFAULT 0,
    created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""

# Minimum messages a session must have before it's worth summarizing
_MIN_MESSAGES_TO_SUMMARIZE = 4

# Maximum facts to inject into the system prompt
_MAX_FACTS_IN_PROMPT = 20

# Number of recent summaries to inject when semantic search is disabled
_RECENT_SUMMARIES_COUNT = 3


class LongTermMemory:
    """
    Persistent long-term memory — facts and session summaries.

    Facts are always injected into the system prompt.
    Session summaries are injected as past context (recent N, or semantic
    search if ChromaDB is available and enabled).
    """

    def __init__(
        self,
        db_path: str = "data/memory.db",
        semantic_search: bool = False,
        chroma_path: str = "data/chroma",
        ollama_url: str = "http://localhost:11434",
    ) -> None:
        self._db_path = db_path
        self._semantic_search = semantic_search
        self._chroma_path = chroma_path
        self._ollama_url = ollama_url
        self._chroma_collection = None  # lazy-loaded if semantic_search=True

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    async def init(self) -> None:
        """Create tables and optionally connect to ChromaDB."""
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(_CREATE_FACTS_TABLE)
            await db.execute(_CREATE_SUMMARIES_TABLE)
            await db.commit()
        logger.debug("LongTermMemory initialised at %s", self._db_path)

        if self._semantic_search:
            await self._init_chromadb()

    async def _init_chromadb(self) -> None:
        """Lazy-load ChromaDB. Silently disables semantic search if unavailable."""
        try:
            import chromadb  # noqa: PLC0415
            import asyncio  # noqa: PLC0415

            Path(self._chroma_path).mkdir(parents=True, exist_ok=True)
            client = await asyncio.to_thread(
                chromadb.PersistentClient, path=self._chroma_path
            )
            self._chroma_collection = await asyncio.to_thread(
                client.get_or_create_collection, "session_summaries"
            )
            logger.info("ChromaDB semantic search enabled at %s", self._chroma_path)
        except ImportError:
            logger.warning(
                "chromadb not installed — falling back to recency-based summary retrieval. "
                "Run: pip install chromadb --break-system-packages"
            )
            self._semantic_search = False
        except Exception as exc:
            logger.warning("ChromaDB init failed (%s) — falling back to recency.", exc)
            self._semantic_search = False

    # ------------------------------------------------------------------
    # Facts
    # ------------------------------------------------------------------

    async def add_fact(self, content: str, category: str = "general") -> int:
        """Store a fact. Returns the new fact ID."""
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "INSERT INTO facts (content, category) VALUES (?, ?)",
                (content.strip(), category.strip()),
            )
            await db.commit()
            return cursor.lastrowid

    async def list_facts(self, category: str | None = None) -> list[dict]:
        """Return all facts, optionally filtered by category."""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            if category:
                async with db.execute(
                    "SELECT id, content, category, created_at FROM facts "
                    "WHERE category = ? ORDER BY id ASC",
                    (category,),
                ) as cursor:
                    rows = await cursor.fetchall()
            else:
                async with db.execute(
                    "SELECT id, content, category, created_at FROM facts ORDER BY id ASC"
                ) as cursor:
                    rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def delete_fact(self, fact_id: int) -> bool:
        """Delete a fact by ID. Returns True if a row was deleted."""
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute("DELETE FROM facts WHERE id = ?", (fact_id,))
            await db.commit()
            return cursor.rowcount > 0

    async def get_facts_for_prompt(self) -> str:
        """
        Return a formatted string of facts for injection into the system prompt.
        Returns empty string if no facts exist.
        """
        facts = await self.list_facts()
        if not facts:
            return ""

        lines = []
        for fact in facts[:_MAX_FACTS_IN_PROMPT]:
            lines.append(f"- {fact['content']}")

        overflow = len(facts) - _MAX_FACTS_IN_PROMPT
        if overflow > 0:
            lines.append(f"...and {overflow} more (use list_facts to see all)")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Session summaries
    # ------------------------------------------------------------------

    async def add_summary(
        self, session_id: str, summary: str, message_count: int
    ) -> None:
        """Store a session summary. Upserts on session_id."""
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """
                INSERT INTO session_summaries (session_id, summary, message_count)
                VALUES (?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    summary = excluded.summary,
                    message_count = excluded.message_count
                """,
                (session_id, summary, message_count),
            )
            await db.commit()

        if self._semantic_search and self._chroma_collection is not None:
            await self._upsert_chroma(session_id, summary)

    async def _upsert_chroma(self, session_id: str, summary: str) -> None:
        """Embed and store a summary in ChromaDB."""
        try:
            import asyncio  # noqa: PLC0415
            import httpx  # noqa: PLC0415

            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{self._ollama_url}/api/embeddings",
                    json={"model": "nomic-embed-text", "prompt": summary},
                )
                resp.raise_for_status()
                embedding = resp.json()["embedding"]

            await asyncio.to_thread(
                self._chroma_collection.upsert,
                ids=[session_id],
                embeddings=[embedding],
                documents=[summary],
            )
        except Exception as exc:
            logger.warning("ChromaDB upsert failed for session %s: %s", session_id, exc)

    async def get_summaries_for_prompt(self, query: str = "") -> str:
        """
        Return formatted recent summaries (or semantically relevant ones if
        ChromaDB is enabled) for injection into the system prompt.
        Returns empty string if no summaries exist.
        """
        if self._semantic_search and self._chroma_collection is not None and query:
            summaries = await self._semantic_search_summaries(query)
        else:
            summaries = await self._recent_summaries()

        if not summaries:
            return ""

        lines = []
        for s in summaries:
            lines.append(f"[{s['session_id']}] {s['summary']}")
        return "\n".join(lines)

    async def _recent_summaries(self) -> list[dict]:
        """Return the N most recent session summaries."""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT session_id, summary FROM session_summaries "
                "ORDER BY created_at DESC LIMIT ?",
                (_RECENT_SUMMARIES_COUNT,),
            ) as cursor:
                rows = await cursor.fetchall()
        return [dict(row) for row in reversed(rows)]  # oldest first

    async def _semantic_search_summaries(self, query: str) -> list[dict]:
        """Find summaries semantically similar to the query via ChromaDB."""
        try:
            import asyncio  # noqa: PLC0415
            import httpx  # noqa: PLC0415

            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{self._ollama_url}/api/embeddings",
                    json={"model": "nomic-embed-text", "prompt": query},
                )
                resp.raise_for_status()
                embedding = resp.json()["embedding"]

            results = await asyncio.to_thread(
                self._chroma_collection.query,
                query_embeddings=[embedding],
                n_results=min(_RECENT_SUMMARIES_COUNT, self._chroma_collection.count()),
            )

            summaries = []
            for sid, doc in zip(results["ids"][0], results["documents"][0]):
                summaries.append({"session_id": sid, "summary": doc})
            return summaries

        except Exception as exc:
            logger.warning("Semantic search failed (%s) — falling back to recency.", exc)
            return await self._recent_summaries()

    # ------------------------------------------------------------------
    # Session summarization helpers (called by Brain)
    # ------------------------------------------------------------------

    async def get_sessions_needing_summary(
        self, current_session_id: str, db_path: str | None = None
    ) -> list[tuple[str, list[dict]]]:
        """
        Find sessions that have enough messages but no summary yet.
        Excludes the current active session.

        Returns a list of (session_id, messages) tuples ready for summarization.
        """
        path = db_path or self._db_path
        async with aiosqlite.connect(path) as db:
            db.row_factory = aiosqlite.Row

            # Sessions that already have summaries
            async with db.execute(
                "SELECT session_id FROM session_summaries"
            ) as cursor:
                summarized = {row["session_id"] for row in await cursor.fetchall()}

            # Sessions with enough messages, excluding current and already summarized
            async with db.execute(
                """
                SELECT session_id, COUNT(*) as msg_count
                FROM messages
                WHERE role IN ('user', 'assistant')
                GROUP BY session_id
                HAVING msg_count >= ?
                """,
                (_MIN_MESSAGES_TO_SUMMARIZE,),
            ) as cursor:
                candidates = [
                    row["session_id"]
                    for row in await cursor.fetchall()
                    if row["session_id"] != current_session_id
                    and row["session_id"] not in summarized
                ]

            # Fetch messages for each candidate
            result = []
            for session_id in candidates:
                async with db.execute(
                    "SELECT role, content FROM messages "
                    "WHERE session_id = ? AND role IN ('user', 'assistant') "
                    "ORDER BY id ASC",
                    (session_id,),
                ) as cursor:
                    messages = [
                        {"role": row["role"], "content": row["content"]}
                        for row in await cursor.fetchall()
                    ]
                result.append((session_id, messages))

        return result
