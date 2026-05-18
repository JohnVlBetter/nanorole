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


def test_database_migrates_legacy_sessions_for_scenario_metadata(tmp_path: Path) -> None:
    db_path = tmp_path / "nanorole.sqlite3"
    with sqlite3.connect(db_path) as connection:
        connection.executescript(
            """
            create table sessions (
              id text primary key,
              user_id text not null,
              companion_id text not null,
              role_id text not null,
              role_name text not null,
              role_version text not null,
              title text,
              status text not null,
              created_at text not null,
              updated_at text not null,
              last_message_at text
            );

            insert into sessions (
              id, user_id, companion_id, role_id, role_name, role_version, title, status,
              created_at, updated_at, last_message_at
            ) values (
              's1', 'local-user', 'clockwork-sage', 'clockwork-sage', 'Clockwork Sage', '1.0.0',
              null, 'active', '2026-05-17T00:00:00+00:00', '2026-05-17T00:00:00+00:00', null
            );
            """
        )

    db = Database(db_path)
    db.initialize()
    db.initialize()

    session_columns = {str(row["name"]) for row in db.fetch_all("pragma table_info(sessions)")}
    participant_columns = {str(row["name"]) for row in db.fetch_all("pragma table_info(session_participants)")}
    story_state_columns = {str(row["name"]) for row in db.fetch_all("pragma table_info(story_states)")}
    row = db.fetch_one("select mode, scenario_id from sessions where id = ?", ("s1",))
    migration_ids = {str(row["id"]) for row in db.fetch_all("select id from schema_migrations order by id")}

    assert {"mode", "scenario_id"} <= session_columns
    assert {"session_id", "role_id", "display_name", "ordinal"} <= participant_columns
    assert {"session_id", "scenario_id", "state_json", "current_scene"} <= story_state_columns
    assert "0003_scenario_sessions" in migration_ids
    assert row is not None
    assert row["mode"] == "companion"
    assert row["scenario_id"] is None


def test_database_creates_scene_events_table(tmp_path: Path) -> None:
    db = Database(tmp_path / "nanorole.sqlite3")

    db.initialize()
    db.initialize()

    columns = {str(row["name"]) for row in db.fetch_all("pragma table_info(scene_events)")}
    migration_ids = {str(row["id"]) for row in db.fetch_all("select id from schema_migrations order by id")}

    assert {"id", "session_id", "type", "payload_json", "created_at", "ordinal"} <= columns
    assert "0004_scene_events" in migration_ids


def test_database_creates_parent_directory(tmp_path: Path) -> None:
    db_path = tmp_path / "nested" / "state" / "nanorole.sqlite3"
    db = Database(db_path)

    db.initialize()

    assert db_path.exists()
