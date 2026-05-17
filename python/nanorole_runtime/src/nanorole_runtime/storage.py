from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Iterable


SCHEMA = """
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
            connection.executescript(SCHEMA)

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
