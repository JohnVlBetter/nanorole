from __future__ import annotations

from pathlib import Path

from nanorole_runtime.memory import MemoryStore
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
