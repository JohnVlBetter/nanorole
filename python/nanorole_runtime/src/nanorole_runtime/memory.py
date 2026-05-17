from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from .storage import Database


VALID_MEMORY_TYPES = {"profile", "preference", "episodic", "relationship", "boundary"}
VALID_MEMORY_STATUS = {"active", "archived", "deleted"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class MemoryRecord:
    memory_id: str
    user_id: str
    companion_id: str
    type: str
    content: str
    importance: float
    confidence: float
    status: str
    created_at: str
    updated_at: str
    last_used_at: str | None
    use_count: int
    source_message_ids: list[str]


class MemoryStore:
    def __init__(self, database: Database) -> None:
        self.database = database

    def create_memory(
        self,
        *,
        user_id: str,
        companion_id: str,
        memory_type: str,
        content: str,
        importance: float,
        confidence: float,
        source_message_ids: list[str],
    ) -> MemoryRecord:
        self._validate(memory_type, content, importance, confidence)
        memory_id = uuid.uuid4().hex
        now = utc_now()
        with self.database.connect() as connection:
            connection.execute(
                """
                insert into memories (
                  id, user_id, companion_id, type, content, importance, confidence,
                  status, created_at, updated_at, last_used_at, use_count
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    memory_id,
                    user_id,
                    companion_id,
                    memory_type,
                    content.strip(),
                    importance,
                    confidence,
                    "active",
                    now,
                    now,
                    None,
                    0,
                ),
            )
            self._replace_sources(connection, memory_id, source_message_ids)
        return self.get_memory(memory_id)

    def list_memories(
        self,
        *,
        user_id: str,
        companion_id: str,
        status: str = "active",
    ) -> list[MemoryRecord]:
        if status not in VALID_MEMORY_STATUS:
            raise ValueError(f"invalid memory status: {status}")
        rows = self.database.fetch_all(
            """
            select *
            from memories
            where user_id = ? and companion_id = ? and status = ?
            order by updated_at desc, created_at desc
            """,
            (user_id, companion_id, status),
        )
        return [self._row_to_memory(row) for row in rows]

    def get_memory(self, memory_id: str) -> MemoryRecord:
        row = self.database.fetch_one("select * from memories where id = ?", (memory_id,))
        if row is None:
            raise KeyError(memory_id)
        return self._row_to_memory(row)

    def update_memory(
        self,
        memory_id: str,
        *,
        memory_type: str | None = None,
        content: str | None = None,
        importance: float | None = None,
        confidence: float | None = None,
        status: str | None = None,
        source_message_ids: list[str] | None = None,
    ) -> MemoryRecord:
        current = self.get_memory(memory_id)
        next_type = memory_type or current.type
        next_content = content if content is not None else current.content
        next_importance = importance if importance is not None else current.importance
        next_confidence = confidence if confidence is not None else current.confidence
        next_status = status or current.status
        self._validate(next_type, next_content, next_importance, next_confidence)
        if next_status not in VALID_MEMORY_STATUS:
            raise ValueError(f"invalid memory status: {next_status}")
        now = utc_now()
        with self.database.connect() as connection:
            connection.execute(
                """
                update memories
                set type = ?, content = ?, importance = ?, confidence = ?, status = ?, updated_at = ?
                where id = ?
                """,
                (
                    next_type,
                    next_content.strip(),
                    next_importance,
                    next_confidence,
                    next_status,
                    now,
                    memory_id,
                ),
            )
            if source_message_ids is not None:
                self._replace_sources(connection, memory_id, source_message_ids)
        return self.get_memory(memory_id)

    def archive_memory(self, memory_id: str) -> MemoryRecord:
        return self.update_memory(memory_id, status="archived")

    def delete_memory(self, memory_id: str) -> MemoryRecord:
        return self.update_memory(memory_id, status="deleted")

    def _row_to_memory(self, row) -> MemoryRecord:
        sources = self.database.fetch_all(
            "select message_id from memory_sources where memory_id = ? order by message_id",
            (row["id"],),
        )
        return MemoryRecord(
            memory_id=str(row["id"]),
            user_id=str(row["user_id"]),
            companion_id=str(row["companion_id"]),
            type=str(row["type"]),
            content=str(row["content"]),
            importance=float(row["importance"]),
            confidence=float(row["confidence"]),
            status=str(row["status"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
            last_used_at=str(row["last_used_at"]) if row["last_used_at"] is not None else None,
            use_count=int(row["use_count"]),
            source_message_ids=[str(source["message_id"]) for source in sources],
        )

    def _validate(self, memory_type: str, content: str, importance: float, confidence: float) -> None:
        if memory_type not in VALID_MEMORY_TYPES:
            raise ValueError(f"invalid memory type: {memory_type}")
        if not content.strip():
            raise ValueError("memory content must be non-empty")
        if not 0.0 <= importance <= 1.0:
            raise ValueError("memory importance must be between 0.0 and 1.0")
        if not 0.0 <= confidence <= 1.0:
            raise ValueError("memory confidence must be between 0.0 and 1.0")

    def _replace_sources(self, connection, memory_id: str, source_message_ids: list[str]) -> None:
        connection.execute("delete from memory_sources where memory_id = ?", (memory_id,))
        for message_id in source_message_ids:
            connection.execute(
                "insert or ignore into memory_sources (memory_id, message_id) values (?, ?)",
                (memory_id, message_id),
            )
