from __future__ import annotations

from pathlib import Path

from nanorole_runtime.context import ContextAssembler
from nanorole_runtime.memory import MemoryStore
from nanorole_runtime.roles import RolePackage
from nanorole_runtime.sessions_types import ChatMessage
from nanorole_runtime.storage import Database


def role() -> RolePackage:
    return RolePackage(
        id="companion",
        name="Companion",
        version="1.0.0",
        world="A quiet room.",
        background="A gentle companion.",
        persona="Warm and concise.",
        goals=["Help the user feel heard."],
        opening="Hello.",
    )


def test_context_includes_relevant_memory(tmp_path: Path) -> None:
    database = Database(tmp_path / "nanorole.sqlite3")
    database.initialize()
    store = MemoryStore(database)
    memory = store.create_memory(
        user_id="local-user",
        companion_id="companion",
        memory_type="preference",
        content="The user prefers gentle reminders.",
        importance=0.9,
        confidence=0.9,
        source_message_ids=[],
    )

    assembler = ContextAssembler(memory_store=store)
    messages, used_memories = assembler.build_messages(
        role=role(),
        user_id="local-user",
        companion_id="companion",
        history=[ChatMessage(role="user", content="Can you remind me how to approach this?")],
        user_input="I need motivation without pressure.",
    )

    joined = "\n".join(item["content"] for item in messages)
    assert "The user prefers gentle reminders." in joined
    assert [item.memory_id for item in used_memories] == [memory.memory_id]


def test_deleted_memory_is_excluded_from_context(tmp_path: Path) -> None:
    database = Database(tmp_path / "nanorole.sqlite3")
    database.initialize()
    store = MemoryStore(database)
    memory = store.create_memory(
        user_id="local-user",
        companion_id="companion",
        memory_type="preference",
        content="The user likes direct pressure.",
        importance=0.9,
        confidence=0.9,
        source_message_ids=[],
    )
    store.delete_memory(memory.memory_id)

    assembler = ContextAssembler(memory_store=store)
    messages, used_memories = assembler.build_messages(
        role=role(),
        user_id="local-user",
        companion_id="companion",
        history=[],
        user_input="Help me plan gently.",
    )

    joined = "\n".join(item["content"] for item in messages)
    assert "The user likes direct pressure." not in joined
    assert used_memories == []


def test_context_includes_relationship_state(tmp_path: Path) -> None:
    database = Database(tmp_path / "nanorole.sqlite3")
    database.initialize()
    store = MemoryStore(database)
    store.upsert_relationship_state(
        user_id="local-user",
        companion_id="companion",
        summary="The user likes calm check-ins and is building trust slowly.",
        familiarity=0.2,
        trust=0.3,
        preferred_address="",
        communication_style="calm check-ins",
    )

    assembler = ContextAssembler(memory_store=store)
    messages, _ = assembler.build_messages(
        role=role(),
        user_id="local-user",
        companion_id="companion",
        history=[],
        user_input="Can we talk for a bit?",
    )

    joined = "\n".join(item["content"] for item in messages)
    assert "calm check-ins" in joined
    assert "building trust slowly" in joined
