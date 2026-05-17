from __future__ import annotations

from pathlib import Path

from nanorole_runtime.memory import MemoryStore, parse_memory_extraction
from nanorole_runtime.storage import Database


def test_memory_store_creates_and_lists_active_memory(tmp_path: Path) -> None:
    database = Database(tmp_path / "nanorole.sqlite3")
    database.initialize()
    store = MemoryStore(database)

    memory = store.create_memory(
        user_id="local-user",
        companion_id="companion",
        memory_type="preference",
        content="The user prefers gentle reminders.",
        importance=0.7,
        confidence=0.9,
        source_message_ids=[],
    )

    memories = store.list_memories(user_id="local-user", companion_id="companion")

    assert len(memories) == 1
    assert memories[0].memory_id == memory.memory_id
    assert memories[0].content == "The user prefers gentle reminders."
    assert memories[0].status == "active"


def test_deleted_memory_is_not_returned_by_default(tmp_path: Path) -> None:
    database = Database(tmp_path / "nanorole.sqlite3")
    database.initialize()
    store = MemoryStore(database)
    memory = store.create_memory(
        user_id="local-user",
        companion_id="companion",
        memory_type="boundary",
        content="The user does not want work stress stored in memory.",
        importance=1.0,
        confidence=1.0,
        source_message_ids=[],
    )

    store.delete_memory(memory.memory_id)

    assert store.list_memories(user_id="local-user", companion_id="companion") == []


def test_parse_memory_extraction_rejects_invalid_type() -> None:
    raw = {
        "memories": [
            {
                "type": "temporary_mood",
                "content": "The user feels tired tonight.",
                "importance": 0.4,
                "confidence": 0.7,
                "source_message_ids": ["m1"],
            }
        ],
        "archive_memory_ids": [],
        "relationship_patch": None,
    }

    try:
        parse_memory_extraction(raw)
    except ValueError as error:
        assert "invalid memory type" in str(error)
    else:
        raise AssertionError("expected invalid memory type to fail")


def test_parse_memory_extraction_accepts_valid_memory() -> None:
    raw = {
        "memories": [
            {
                "type": "preference",
                "content": "The user prefers gentle reminders.",
                "importance": 0.7,
                "confidence": 0.8,
                "source_message_ids": ["m1"],
            }
        ],
        "archive_memory_ids": [],
        "relationship_patch": None,
    }

    parsed = parse_memory_extraction(raw)

    assert parsed.memories[0].content == "The user prefers gentle reminders."
