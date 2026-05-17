from __future__ import annotations

import sqlite3
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


def test_database_migrates_legacy_message_table(tmp_path: Path) -> None:
    db_path = tmp_path / "nanorole.sqlite3"
    with sqlite3.connect(db_path) as connection:
        connection.executescript(
            """
            create table messages (
              id text primary key,
              session_id text not null,
              role text not null,
              content text not null,
              created_at text not null,
              ordinal integer not null
            );

            insert into messages (id, session_id, role, content, created_at, ordinal)
            values ('m1', 's1', 'user', 'old hello', '2026-05-17T00:00:00+00:00', 0);
            """
        )

    db = Database(db_path)
    db.initialize()
    db.initialize()

    columns = {
        str(row["name"])
        for row in db.fetch_all("pragma table_info(messages)")
    }
    migration_ids = {
        str(row["id"])
        for row in db.fetch_all("select id from schema_migrations order by id")
    }
    row = db.fetch_one("select content, speaker_id, input_modality from messages where id = ?", ("m1",))

    assert {"speaker_id", "input_modality", "output_modality", "emotion_label", "audio_ref"} <= columns
    assert {"0001_initial_schema", "0002_message_metadata"} <= migration_ids
    assert row is not None
    assert row["content"] == "old hello"
    assert row["speaker_id"] is None
    assert row["input_modality"] is None


def test_database_creates_parent_directory(tmp_path: Path) -> None:
    db_path = tmp_path / "nested" / "state" / "nanorole.sqlite3"
    db = Database(db_path)

    db.initialize()

    assert db_path.exists()
