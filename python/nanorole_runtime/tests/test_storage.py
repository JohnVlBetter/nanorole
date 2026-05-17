from __future__ import annotations

from pathlib import Path

from nanorole_runtime.storage import Database


def test_database_initializes_schema_idempotently(tmp_path: Path) -> None:
    db_path = tmp_path / "nanorole.sqlite3"
    db = Database(db_path)

    db.initialize()
    db.initialize()

    tables = db.table_names()
    assert "users" in tables
    assert "companions" in tables
    assert "sessions" in tables
    assert "messages" in tables
    assert "session_events" in tables
    assert "conversation_summaries" in tables
    assert "memories" in tables
    assert "memory_sources" in tables
    assert "relationship_states" in tables


def test_database_creates_parent_directory(tmp_path: Path) -> None:
    db_path = tmp_path / "nested" / "state" / "nanorole.sqlite3"
    db = Database(db_path)

    db.initialize()

    assert db_path.exists()
