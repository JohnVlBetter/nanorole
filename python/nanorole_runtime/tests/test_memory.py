from __future__ import annotations

from pathlib import Path

from nanorole_runtime.config import load_config
from nanorole_runtime.memory import MemoryExtractor, MemoryStore, parse_memory_extraction
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
        source_message_ids=["m1"],
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
        source_message_ids=["m1"],
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


def test_parse_memory_extraction_rejects_empty_source_messages() -> None:
    raw = {
        "memories": [
            {
                "type": "preference",
                "content": "The user prefers gentle reminders.",
                "importance": 0.7,
                "confidence": 0.8,
                "source_message_ids": [],
            }
        ],
        "archive_memory_ids": [],
        "relationship_patch": None,
    }

    try:
        parse_memory_extraction(raw)
    except ValueError as error:
        assert "source_message_ids must include at least one source message id" in str(error)
    else:
        raise AssertionError("expected empty source messages to fail")


def test_memory_store_requires_source_messages(tmp_path: Path) -> None:
    database = Database(tmp_path / "nanorole.sqlite3")
    database.initialize()
    store = MemoryStore(database)

    try:
        store.create_memory(
            user_id="local-user",
            companion_id="companion",
            memory_type="preference",
            content="The user prefers gentle reminders.",
            importance=0.7,
            confidence=0.9,
            source_message_ids=[],
        )
    except ValueError as error:
        assert "source message id" in str(error)
    else:
        raise AssertionError("expected memory creation without source messages to fail")


def test_parse_memory_extraction_normalizes_common_score_labels() -> None:
    raw = {
        "memories": [
            {
                "type": "preference",
                "content": "The user prefers cola.",
                "importance": "high",
                "confidence": "medium",
                "source_message_ids": ["m1"],
            }
        ],
        "archive_memory_ids": [],
        "relationship_patch": None,
    }

    parsed = parse_memory_extraction(raw)

    assert parsed.memories[0].importance == 0.8
    assert parsed.memories[0].confidence == 0.6


def test_parse_memory_extraction_normalizes_chinese_score_variants() -> None:
    raw = {
        "memories": [
            {
                "type": "preference",
                "content": "The user wants souffle prepared first on future visits.",
                "importance": "较高",
                "confidence": "高（用户明确要求记住）",
                "source_message_ids": ["m1"],
            }
        ],
        "archive_memory_ids": [],
        "relationship_patch": None,
    }

    parsed = parse_memory_extraction(raw)

    assert parsed.memories[0].importance == 0.8
    assert parsed.memories[0].confidence == 0.8


def test_parse_memory_extraction_tolerates_llm_score_annotations() -> None:
    raw = {
        "memories": [
            {
                "type": "preference",
                "content": "The user wants souffle prepared first on future visits.",
                "importance": "0.8 - explicit request",
                "confidence": "确认：用户明确要求记住",
                "source_message_ids": ["m1"],
            }
        ],
        "archive_memory_ids": [],
        "relationship_patch": None,
    }

    parsed = parse_memory_extraction(raw)

    assert parsed.memories[0].importance == 0.8
    assert parsed.memories[0].confidence == 0.6


def test_parse_memory_extraction_tolerates_structured_score_labels() -> None:
    raw = {
        "memories": [
            {
                "type": "preference",
                "content": "The user wants cola prepared on future visits.",
                "importance": {"label": "high", "reason": "explicit request"},
                "confidence": {"value": "0.7"},
                "source_message_ids": ["m1"],
            }
        ],
        "archive_memory_ids": [],
        "relationship_patch": None,
    }

    parsed = parse_memory_extraction(raw)

    assert parsed.memories[0].importance == 0.8
    assert parsed.memories[0].confidence == 0.7


async def test_memory_extractor_adds_explicit_remember_request_when_model_omits_memory(tmp_path: Path) -> None:
    class OmittingClient:
        async def complete_json(self, *, messages, config):
            return {
                "memories": [],
                "archive_memory_ids": [],
                "relationship_patch": None,
            }

    database = Database(tmp_path / "nanorole.sqlite3")
    database.initialize()
    extractor = MemoryExtractor(
        client=OmittingClient(),
        config=load_config(repo_root=tmp_path),
        store=MemoryStore(database),
    )

    extraction = await extractor.extract_after_turn(
        user_id="local-user",
        companion_id="neko-maid",
        user_message_id="m1",
        user_message="以后记得给我准备舒芙蕾和可乐",
        assistant_message_id="a1",
        assistant_message="记住了。",
    )

    assert len(extraction.memories) == 1
    memory = extraction.memories[0]
    assert memory.type == "preference"
    assert "舒芙蕾" in memory.content
    assert "可乐" in memory.content
    assert memory.source_message_ids == ["m1"]


def test_temporary_mood_fixture_writes_no_long_term_memory(tmp_path: Path) -> None:
    database = Database(tmp_path / "nanorole.sqlite3")
    database.initialize()
    store = MemoryStore(database)
    extraction = parse_memory_extraction({"memories": [], "archive_memory_ids": [], "relationship_patch": None})

    written = store.apply_extraction(user_id="local-user", companion_id="companion", extraction=extraction)

    assert written == []
    assert store.list_memories(user_id="local-user", companion_id="companion") == []


def test_sensitive_health_fixture_writes_no_memory_without_explicit_request(tmp_path: Path) -> None:
    database = Database(tmp_path / "nanorole.sqlite3")
    database.initialize()
    store = MemoryStore(database)
    extraction = parse_memory_extraction({"memories": [], "archive_memory_ids": [], "relationship_patch": None})

    written = store.apply_extraction(user_id="local-user", companion_id="companion", extraction=extraction)

    assert written == []
    assert store.list_memories(user_id="local-user", companion_id="companion") == []


def test_explicit_preference_fixture_writes_memory(tmp_path: Path) -> None:
    database = Database(tmp_path / "nanorole.sqlite3")
    database.initialize()
    store = MemoryStore(database)
    extraction = parse_memory_extraction(
        {
            "memories": [
                {
                    "type": "preference",
                    "content": "The user prefers gentle reminders.",
                    "importance": 0.7,
                    "confidence": 0.9,
                    "source_message_ids": ["m1"],
                }
            ],
            "archive_memory_ids": [],
            "relationship_patch": None,
        }
    )

    written = store.apply_extraction(user_id="local-user", companion_id="companion", extraction=extraction)

    assert [memory.content for memory in written] == ["The user prefers gentle reminders."]
    assert store.list_memories(user_id="local-user", companion_id="companion")[0].source_message_ids == ["m1"]


def test_explicit_boundary_fixture_writes_boundary_memory(tmp_path: Path) -> None:
    database = Database(tmp_path / "nanorole.sqlite3")
    database.initialize()
    store = MemoryStore(database)
    extraction = parse_memory_extraction(
        {
            "memories": [
                {
                    "type": "boundary",
                    "content": "The user does not want work stress saved as memory.",
                    "importance": 1.0,
                    "confidence": 1.0,
                    "source_message_ids": ["m1"],
                }
            ],
            "archive_memory_ids": [],
            "relationship_patch": None,
        }
    )

    written = store.apply_extraction(user_id="local-user", companion_id="companion", extraction=extraction)

    assert written[0].type == "boundary"
    assert written[0].content == "The user does not want work stress saved as memory."


def test_correction_fixture_archives_old_memory_and_writes_new_one(tmp_path: Path) -> None:
    database = Database(tmp_path / "nanorole.sqlite3")
    database.initialize()
    store = MemoryStore(database)
    old = store.create_memory(
        user_id="local-user",
        companion_id="companion",
        memory_type="preference",
        content="The user prefers direct pressure.",
        importance=0.7,
        confidence=0.7,
        source_message_ids=["m1"],
    )
    extraction = parse_memory_extraction(
        {
            "memories": [
                {
                    "type": "preference",
                    "content": "The user prefers gentle reminders.",
                    "importance": 0.8,
                    "confidence": 0.95,
                    "source_message_ids": ["m2"],
                }
            ],
            "archive_memory_ids": [old.memory_id],
            "relationship_patch": None,
        }
    )

    written = store.apply_extraction(user_id="local-user", companion_id="companion", extraction=extraction)

    assert store.get_memory(old.memory_id).status == "archived"
    assert [memory.content for memory in written] == ["The user prefers gentle reminders."]
