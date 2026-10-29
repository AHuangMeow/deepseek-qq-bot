"""Small SQLite conversation store."""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class StoredMessage:
    role: str  # "user" | "assistant"
    sender_name: str
    user_id: int | None
    content: str
    created_at: float
    message_id: str | None


class Memory:
    def __init__(self, path: Path, *, keep_per_conversation: int = 240):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.keep_per_conversation = keep_per_conversation
        self.conn = sqlite3.connect(path)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self._init_schema()
        self._writes = 0

    def _init_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL,
                role TEXT NOT NULL,
                sender_name TEXT NOT NULL DEFAULT '',
                user_id INTEGER,
                content TEXT NOT NULL,
                message_id TEXT,
                created_at REAL NOT NULL
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_messages_message_id
                ON messages(message_id) WHERE message_id IS NOT NULL;
            CREATE INDEX IF NOT EXISTS idx_messages_conversation
                ON messages(conversation_id, id);

            CREATE TABLE IF NOT EXISTS conversations (
                conversation_id TEXT PRIMARY KEY,
                last_reply_at REAL,
                last_message_at REAL
            );
            """
        )
        self.conn.commit()

    def add_message(
        self,
        conversation_id: str,
        role: str,
        sender_name: str,
        user_id: int | None,
        content: str,
        message_id: str | None = None,
        *,
        created_at: float | None = None,
    ) -> bool:
        """Insert a message. Returns False when this message_id was already stored."""
        now = time.time() if created_at is None else created_at
        cur = self.conn.execute(
            """
            INSERT OR IGNORE INTO messages
                (conversation_id, role, sender_name, user_id, content, message_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (conversation_id, role, sender_name, user_id, content, message_id, now),
        )
        inserted = cur.rowcount > 0
        if inserted:
            self.conn.execute(
                """
                INSERT INTO conversations (conversation_id, last_message_at)
                VALUES (?, ?)
                ON CONFLICT(conversation_id) DO UPDATE SET last_message_at=excluded.last_message_at
                """,
                (conversation_id, now),
            )
            self.conn.commit()
            self._writes += 1
            if self._writes % 100 == 0:
                self.cleanup()
        return inserted

    def update_message_content(self, conversation_id: str, message_id: str, content: str) -> None:
        """Enrich a stored user message with image captions."""
        self.conn.execute(
            "UPDATE messages SET content = ? WHERE conversation_id = ? AND message_id = ?",
            (content, conversation_id, message_id),
        )
        self.conn.commit()

    def recent(self, conversation_id: str, limit: int) -> list[StoredMessage]:
        rows = self.conn.execute(
            """
            SELECT role, sender_name, user_id, content, created_at, message_id
            FROM messages
            WHERE conversation_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (conversation_id, limit),
        ).fetchall()
        rows.reverse()
        return [
            StoredMessage(
                role=str(row[0]),
                sender_name=str(row[1]),
                user_id=row[2],
                content=str(row[3]),
                created_at=float(row[4]),
                message_id=row[5],
            )
            for row in rows
        ]

    def latest_user_message_id(self, conversation_id: str) -> str | None:
        row = self.conn.execute(
            """
            SELECT message_id FROM messages
            WHERE conversation_id = ? AND role = 'user'
            ORDER BY id DESC LIMIT 1
            """,
            (conversation_id,),
        ).fetchone()
        return None if row is None else row[0]

    def bot_messages_in_row(self, conversation_id: str, lookback: int = 6) -> int:
        rows = self.conn.execute(
            """
            SELECT role FROM messages
            WHERE conversation_id = ?
            ORDER BY id DESC LIMIT ?
            """,
            (conversation_id, lookback),
        ).fetchall()
        count = 0
        for (role,) in rows:
            if role == "assistant":
                count += 1
            else:
                break
        return count

    def seconds_since_last_reply(self, conversation_id: str) -> float | None:
        row = self.conn.execute(
            "SELECT last_reply_at FROM conversations WHERE conversation_id = ?",
            (conversation_id,),
        ).fetchone()
        if row is None or row[0] is None:
            return None
        return max(0.0, time.time() - float(row[0]))

    def seconds_since_last_message(self, conversation_id: str) -> float | None:
        row = self.conn.execute(
            "SELECT last_message_at FROM conversations WHERE conversation_id = ?",
            (conversation_id,),
        ).fetchone()
        if row is None or row[0] is None:
            return None
        return max(0.0, time.time() - float(row[0]))

    def set_last_reply(self, conversation_id: str, when: float | None = None) -> None:
        now = time.time() if when is None else when
        self.conn.execute(
            """
            INSERT INTO conversations (conversation_id, last_reply_at)
            VALUES (?, ?)
            ON CONFLICT(conversation_id) DO UPDATE SET last_reply_at=excluded.last_reply_at
            """,
            (conversation_id, now),
        )
        self.conn.commit()

    def clear(self, conversation_id: str) -> int:
        cur = self.conn.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
        self.conn.commit()
        return cur.rowcount

    def cleanup(self) -> None:
        convs = self.conn.execute("SELECT DISTINCT conversation_id FROM messages").fetchall()
        for (conversation_id,) in convs:
            self.conn.execute(
                """
                DELETE FROM messages
                WHERE conversation_id = ?
                  AND id NOT IN (
                      SELECT id FROM messages
                      WHERE conversation_id = ?
                      ORDER BY id DESC
                      LIMIT ?
                  )
                """,
                (conversation_id, conversation_id, self.keep_per_conversation),
            )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()
