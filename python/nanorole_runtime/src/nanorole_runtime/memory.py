from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .config import AppConfig
from .llm import ChatClient
from .storage import Database


VALID_MEMORY_TYPES = {"profile", "preference", "episodic", "relationship", "boundary"}
VALID_MEMORY_STATUS = {"active", "archived", "deleted"}
SCORE_LABELS = {
    "very low": 0.2,
    "low": 0.3,
    "medium": 0.6,
    "moderate": 0.6,
    "high": 0.8,
    "very high": 0.95,
    "低": 0.3,
    "中": 0.6,
    "中等": 0.6,
    "一般": 0.6,
    "高": 0.8,
    "很高": 0.95,
}


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


@dataclass(frozen=True)
class ExtractedMemory:
    type: str
    content: str
    importance: float
    confidence: float
    source_message_ids: list[str]


@dataclass(frozen=True)
class RelationshipPatch:
    summary: str | None
    familiarity_delta: float
    trust_delta: float
    preferred_address: str | None
    communication_style: str | None


@dataclass(frozen=True)
class MemoryExtraction:
    memories: list[ExtractedMemory]
    archive_memory_ids: list[str]
    relationship_patch: RelationshipPatch | None


@dataclass(frozen=True)
class RelationshipState:
    user_id: str
    companion_id: str
    summary: str
    familiarity: float
    trust: float
    preferred_address: str | None
    communication_style: str | None
    updated_at: str


def parse_memory_extraction(raw: dict[str, object]) -> MemoryExtraction:
    memories_raw = raw.get("memories")
    if not isinstance(memories_raw, list):
        raise ValueError("memories must be a list")
    archive_raw = raw.get("archive_memory_ids", [])
    if not isinstance(archive_raw, list) or not all(isinstance(item, str) for item in archive_raw):
        raise ValueError("archive_memory_ids must be a list of strings")

    memories: list[ExtractedMemory] = []
    for item in memories_raw:
        if not isinstance(item, dict):
            raise ValueError("memory item must be an object")
        memory_type = _required_string(item, "type")
        if memory_type not in VALID_MEMORY_TYPES:
            raise ValueError(f"invalid memory type: {memory_type}")
        content = _required_string(item, "content")
        importance = _required_float(item, "importance")
        confidence = _required_float(item, "confidence")
        source_message_ids = item.get("source_message_ids")
        if not isinstance(source_message_ids, list) or not all(isinstance(source, str) for source in source_message_ids):
            raise ValueError("source_message_ids must be a list of strings")
        _validate_score("importance", importance)
        _validate_score("confidence", confidence)
        memories.append(
            ExtractedMemory(
                type=memory_type,
                content=content.strip(),
                importance=importance,
                confidence=confidence,
                source_message_ids=list(source_message_ids),
            )
        )

    relationship_raw = raw.get("relationship_patch")
    relationship_patch = _parse_relationship_patch(relationship_raw)
    return MemoryExtraction(
        memories=memories,
        archive_memory_ids=list(archive_raw),
        relationship_patch=relationship_patch,
    )


class MemoryExtractor:
    def __init__(self, *, client: ChatClient, config: AppConfig, store: "MemoryStore") -> None:
        self.client = client
        self.config = config
        self.store = store

    async def extract_after_turn(
        self,
        *,
        user_id: str,
        companion_id: str,
        user_message_id: str,
        user_message: str,
        assistant_message_id: str,
        assistant_message: str,
    ) -> MemoryExtraction:
        existing = self.store.list_memories(user_id=user_id, companion_id=companion_id)
        existing_text = "\n".join(f"- {memory.memory_id}: [{memory.type}] {memory.content}" for memory in existing)
        if not existing_text:
            existing_text = "- none"
        raw = await self.client.complete_json(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Extract only durable long-term memories for a local emotional companion. "
                        "Do not store temporary emotions unless the user explicitly asks. "
                        "Do not store sensitive health, crisis, sexual, financial, legal, address, credential, "
                        "or third-party private information unless the user explicitly asks to remember it. "
                        "Return strict JSON with keys memories, archive_memory_ids, relationship_patch. "
                        "Use only memory types: profile, preference, episodic, relationship, boundary. "
                        "Use only the provided source message ids."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"user_id: {user_id}\n"
                        f"companion_id: {companion_id}\n"
                        f"existing_memories:\n{existing_text}\n\n"
                        f"user_message_id: {user_message_id}\n"
                        f"user_message: {user_message}\n\n"
                        f"assistant_message_id: {assistant_message_id}\n"
                        f"assistant_message: {assistant_message}"
                    ),
                },
            ],
            config=self.config,
        )
        return parse_memory_extraction(raw)


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

    def mark_used(self, memory_ids: list[str]) -> None:
        if not memory_ids:
            return
        now = utc_now()
        with self.database.connect() as connection:
            for memory_id in memory_ids:
                connection.execute(
                    "update memories set last_used_at = ?, use_count = use_count + 1 where id = ?",
                    (now, memory_id),
                )

    def apply_extraction(
        self,
        *,
        user_id: str,
        companion_id: str,
        extraction: MemoryExtraction,
    ) -> list[MemoryRecord]:
        written: list[MemoryRecord] = []
        for memory_id in extraction.archive_memory_ids:
            try:
                current = self.get_memory(memory_id)
            except KeyError:
                continue
            if current.status == "active":
                self.archive_memory(memory_id)

        active = self.list_memories(user_id=user_id, companion_id=companion_id)
        by_content = {memory.content.strip().lower(): memory for memory in active}
        for extracted in extraction.memories:
            existing = by_content.get(extracted.content.strip().lower())
            if existing is not None:
                merged_sources = sorted({*existing.source_message_ids, *extracted.source_message_ids})
                updated = self.update_memory(
                    existing.memory_id,
                    memory_type=existing.type,
                    content=existing.content,
                    importance=max(existing.importance, extracted.importance),
                    confidence=max(existing.confidence, extracted.confidence),
                    source_message_ids=merged_sources,
                )
                written.append(updated)
                continue
            created = self.create_memory(
                user_id=user_id,
                companion_id=companion_id,
                memory_type=extracted.type,
                content=extracted.content,
                importance=extracted.importance,
                confidence=extracted.confidence,
                source_message_ids=extracted.source_message_ids,
            )
            by_content[created.content.strip().lower()] = created
            written.append(created)
        if extraction.relationship_patch is not None:
            self.apply_relationship_patch(
                user_id=user_id,
                companion_id=companion_id,
                patch=extraction.relationship_patch,
            )
        return written

    def get_relationship_state(self, *, user_id: str, companion_id: str) -> RelationshipState | None:
        row = self.database.fetch_one(
            "select * from relationship_states where user_id = ? and companion_id = ?",
            (user_id, companion_id),
        )
        if row is None:
            return None
        return RelationshipState(
            user_id=str(row["user_id"]),
            companion_id=str(row["companion_id"]),
            summary=str(row["summary"]),
            familiarity=float(row["familiarity"]),
            trust=float(row["trust"]),
            preferred_address=str(row["preferred_address"]) if row["preferred_address"] is not None else None,
            communication_style=str(row["communication_style"]) if row["communication_style"] is not None else None,
            updated_at=str(row["updated_at"]),
        )

    def upsert_relationship_state(
        self,
        *,
        user_id: str,
        companion_id: str,
        summary: str,
        familiarity: float,
        trust: float,
        preferred_address: str | None,
        communication_style: str | None,
    ) -> RelationshipState:
        now = utc_now()
        with self.database.connect() as connection:
            connection.execute(
                """
                insert into relationship_states (
                  user_id, companion_id, summary, familiarity, trust,
                  preferred_address, communication_style, updated_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(user_id, companion_id) do update set
                  summary = excluded.summary,
                  familiarity = excluded.familiarity,
                  trust = excluded.trust,
                  preferred_address = excluded.preferred_address,
                  communication_style = excluded.communication_style,
                  updated_at = excluded.updated_at
                """,
                (
                    user_id,
                    companion_id,
                    summary.strip(),
                    _clamp(familiarity),
                    _clamp(trust),
                    preferred_address.strip() if preferred_address else None,
                    communication_style.strip() if communication_style else None,
                    now,
                ),
            )
        state = self.get_relationship_state(user_id=user_id, companion_id=companion_id)
        if state is None:
            raise KeyError((user_id, companion_id))
        return state

    def apply_relationship_patch(
        self,
        *,
        user_id: str,
        companion_id: str,
        patch: RelationshipPatch,
    ) -> RelationshipState:
        current = self.get_relationship_state(user_id=user_id, companion_id=companion_id)
        if current is None:
            return self.upsert_relationship_state(
                user_id=user_id,
                companion_id=companion_id,
                summary=patch.summary or "",
                familiarity=_clamp(patch.familiarity_delta),
                trust=_clamp(patch.trust_delta),
                preferred_address=patch.preferred_address,
                communication_style=patch.communication_style,
            )
        return self.upsert_relationship_state(
            user_id=user_id,
            companion_id=companion_id,
            summary=patch.summary or current.summary,
            familiarity=_clamp(current.familiarity + patch.familiarity_delta),
            trust=_clamp(current.trust + patch.trust_delta),
            preferred_address=patch.preferred_address or current.preferred_address,
            communication_style=patch.communication_style or current.communication_style,
        )

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


def _required_string(item: dict[Any, Any], key: str) -> str:
    value = item.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _required_float(item: dict[Any, Any], key: str) -> float:
    value = item.get(key)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in SCORE_LABELS:
            return SCORE_LABELS[normalized]
        if normalized.endswith("%"):
            try:
                return float(normalized.removesuffix("%")) / 100
            except ValueError:
                pass
        try:
            return float(normalized)
        except ValueError:
            pass
    raise ValueError(f"{key} must be a number")


def _validate_score(key: str, value: float) -> None:
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"{key} must be between 0.0 and 1.0")


def _parse_relationship_patch(value: object) -> RelationshipPatch | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("relationship_patch must be an object or null")
    return RelationshipPatch(
        summary=_optional_string(value.get("summary")),
        familiarity_delta=_optional_float(value.get("familiarity_delta"), 0.0),
        trust_delta=_optional_float(value.get("trust_delta"), 0.0),
        preferred_address=_optional_string(value.get("preferred_address")),
        communication_style=_optional_string(value.get("communication_style")),
    )


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("relationship string fields must be strings or null")
    return value.strip() or None


def _optional_float(value: object, default: float) -> float:
    if value is None:
        return default
    if not isinstance(value, (int, float)):
        raise ValueError("relationship delta fields must be numbers")
    return float(value)


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))
