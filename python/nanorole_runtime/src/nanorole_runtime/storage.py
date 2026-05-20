from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable


SCHEMA_MIGRATIONS_TABLE = """
create table if not exists schema_migrations (
  id text primary key,
  applied_at text not null
);
"""

INITIAL_SCHEMA = """
create table if not exists users (
  id text primary key,
  display_name text not null,
  created_at text not null,
  updated_at text not null
);

create table if not exists companions (
  id text primary key,
  role_id text not null,
  role_version text not null,
  display_name text not null,
  created_at text not null,
  updated_at text not null
);

create table if not exists sessions (
  id text primary key,
  user_id text not null,
  companion_id text not null,
  role_id text not null,
  role_name text not null,
  role_version text not null,
  mode text not null default 'companion',
  scenario_id text,
  scenario_name text,
  title text,
  status text not null,
  created_at text not null,
  updated_at text not null,
  last_message_at text
);

create table if not exists messages (
  id text primary key,
  session_id text not null,
  role text not null,
  content text not null,
  created_at text not null,
  ordinal integer not null
);

create index if not exists idx_messages_session_ordinal on messages(session_id, ordinal);

create table if not exists session_events (
  id text primary key,
  session_id text,
  type text not null,
  payload_json text not null,
  created_at text not null
);

create index if not exists idx_session_events_session_created on session_events(session_id, created_at);

create table if not exists conversation_summaries (
  id text primary key,
  session_id text not null,
  covered_until_message_id text not null,
  summary text not null,
  created_at text not null,
  updated_at text not null
);

create table if not exists memories (
  id text primary key,
  user_id text not null,
  companion_id text not null,
  type text not null,
  content text not null,
  importance real not null,
  confidence real not null,
  status text not null,
  created_at text not null,
  updated_at text not null,
  last_used_at text,
  use_count integer not null default 0
);

create index if not exists idx_memories_owner_status on memories(user_id, companion_id, status);

create table if not exists memory_sources (
  memory_id text not null,
  message_id text not null,
  primary key (memory_id, message_id)
);

create table if not exists relationship_states (
  user_id text not null,
  companion_id text not null,
  summary text not null,
  familiarity real not null,
  trust real not null,
  preferred_address text,
  communication_style text,
  updated_at text not null,
  primary key (user_id, companion_id)
);
"""

MESSAGE_METADATA_COLUMNS = {
    "speaker_id": "speaker_id text",
    "input_modality": "input_modality text",
    "output_modality": "output_modality text",
    "emotion_label": "emotion_label text",
    "audio_ref": "audio_ref text",
}

SESSION_SCENARIO_COLUMNS = {
    "mode": "mode text not null default 'companion'",
    "scenario_id": "scenario_id text",
    "scenario_name": "scenario_name text",
}

PARTICIPANT_METADATA_COLUMNS = {
    "status": "status text not null default 'active'",
    "visibility_json": "visibility_json text not null default '{}'",
}

Migration = tuple[str, Callable[[sqlite3.Connection], None]]


def _apply_initial_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(INITIAL_SCHEMA)


def _apply_message_metadata(connection: sqlite3.Connection) -> None:
    existing_columns = _column_names(connection, "messages")
    for column_name, definition in MESSAGE_METADATA_COLUMNS.items():
        if column_name not in existing_columns:
            connection.execute(f"alter table messages add column {definition}")


def _apply_scenario_sessions(connection: sqlite3.Connection) -> None:
    existing_columns = _column_names(connection, "sessions")
    for column_name, definition in SESSION_SCENARIO_COLUMNS.items():
        if column_name not in existing_columns:
            connection.execute(f"alter table sessions add column {definition}")
    connection.executescript(
        """
        create table if not exists session_participants (
          session_id text not null,
          role_id text not null,
          display_name text not null,
          ordinal integer not null,
          primary key (session_id, role_id)
        );

        create index if not exists idx_session_participants_session_ordinal
        on session_participants(session_id, ordinal);

        create table if not exists story_states (
          session_id text primary key,
          scenario_id text not null,
          state_json text not null,
          current_scene text not null,
          created_at text not null,
          updated_at text not null
        );
        """
    )


def _apply_scene_events(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        create table if not exists scene_events (
          id text primary key,
          session_id text not null,
          type text not null,
          payload_json text not null,
          created_at text not null,
          ordinal integer not null
        );

        create index if not exists idx_scene_events_session_ordinal
        on scene_events(session_id, ordinal);
        """
    )


def _apply_participant_metadata(connection: sqlite3.Connection) -> None:
    existing_columns = _column_names(connection, "session_participants")
    for column_name, definition in PARTICIPANT_METADATA_COLUMNS.items():
        if column_name not in existing_columns:
            connection.execute(f"alter table session_participants add column {definition}")


MIGRATIONS: tuple[Migration, ...] = (
    ("0001_initial_schema", _apply_initial_schema),
    ("0002_message_metadata", _apply_message_metadata),
    ("0003_scenario_sessions", _apply_scenario_sessions),
    ("0004_scene_events", _apply_scene_events),
    ("0005_participant_metadata", _apply_participant_metadata),
)


class Database:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("pragma foreign_keys = on")
        return connection

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(SCHEMA_MIGRATIONS_TABLE)
            applied = {
                str(row["id"])
                for row in connection.execute("select id from schema_migrations").fetchall()
            }
            for migration_id, apply_migration in MIGRATIONS:
                if migration_id in applied:
                    continue
                apply_migration(connection)
                connection.execute(
                    "insert into schema_migrations (id, applied_at) values (?, ?)",
                    (migration_id, datetime.now(timezone.utc).isoformat()),
                )

    def table_names(self) -> set[str]:
        with self.connect() as connection:
            rows = connection.execute("select name from sqlite_master where type = 'table'").fetchall()
        return {str(row["name"]) for row in rows}

    def execute(self, sql: str, parameters: Iterable[Any] = ()) -> None:
        with self.connect() as connection:
            connection.execute(sql, tuple(parameters))

    def fetch_all(self, sql: str, parameters: Iterable[Any] = ()) -> list[sqlite3.Row]:
        with self.connect() as connection:
            return list(connection.execute(sql, tuple(parameters)).fetchall())

    def fetch_one(self, sql: str, parameters: Iterable[Any] = ()) -> sqlite3.Row | None:
        with self.connect() as connection:
            return connection.execute(sql, tuple(parameters)).fetchone()


def _column_names(connection: sqlite3.Connection, table_name: str) -> set[str]:
    rows = connection.execute(f"pragma table_info({table_name})").fetchall()
    return {str(row["name"]) for row in rows}
