from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .sessions_types import ChatMessage
from .storage import Database


VALID_SESSION_STATUS = {"active", "archived", "deleted"}


@dataclass
class StoredSession:
    session_id: str
    role_id: str
    role_name: str
    role_version: str
    mode: str
    companion_id: str
    scenario_id: str | None = None
    scenario_name: str | None = None
    title: str | None = None
    status: str = "active"
    created_at: str | None = None
    updated_at: str | None = None
    last_message_at: str | None = None
    history: list[ChatMessage] = field(default_factory=list)


class SessionStore:
    def __init__(self, database: Database) -> None:
        self.database = database

    def create_session(
        self,
        *,
        user_id: str,
        companion_id: str,
        role_id: str,
        role_name: str,
        role_version: str,
        mode: str,
        scenario_id: str | None,
        scenario_name: str | None,
    ) -> StoredSession:
        now = _now()
        session_id = uuid.uuid4().hex
        with self.database.connect() as connection:
            connection.execute(
                """
                insert into users (id, display_name, created_at, updated_at)
                values (?, ?, ?, ?)
                on conflict(id) do update set updated_at = excluded.updated_at
                """,
                (user_id, "Local User", now, now),
            )
            connection.execute(
                """
                insert into companions (id, role_id, role_version, display_name, created_at, updated_at)
                values (?, ?, ?, ?, ?, ?)
                on conflict(id) do update set
                  role_version = excluded.role_version,
                  display_name = excluded.display_name,
                  updated_at = excluded.updated_at
                """,
                (companion_id, role_id, role_version, role_name, now, now),
            )
            connection.execute(
                """
                insert into sessions (
                  id, user_id, companion_id, role_id, role_name, role_version, mode, scenario_id, scenario_name,
                  title, status, created_at, updated_at, last_message_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    user_id,
                    companion_id,
                    role_id,
                    role_name,
                    role_version,
                    mode,
                    scenario_id,
                    scenario_name,
                    None,
                    "active",
                    now,
                    now,
                    None,
                ),
            )
        return self.get_session(session_id)

    def get_session(self, session_id: str) -> StoredSession:
        row = self.database.fetch_one("select * from sessions where id = ? and status != 'deleted'", (session_id,))
        if row is None:
            raise KeyError(session_id)
        return self._session_from_row(row, include_history=True)

    def list_sessions(self) -> list[StoredSession]:
        rows = self.database.fetch_all(
            """
            select *
            from sessions
            where status != 'deleted'
            order by coalesce(last_message_at, created_at) desc, created_at desc
            """
        )
        return [self._session_from_row(row, include_history=True) for row in rows]

    def update_session(self, session_id: str, *, title: str | None, status: str | None) -> StoredSession:
        current = self.get_session(session_id)
        next_title = title if title is not None else current.title
        next_status = status if status is not None else current.status
        if next_status not in VALID_SESSION_STATUS:
            raise ValueError(f"invalid session status: {next_status}")
        now = _now()
        self.database.execute(
            """
            update sessions
            set title = ?, status = ?, updated_at = ?
            where id = ?
            """,
            (next_title, next_status, now, session_id),
        )
        return self.get_session(session_id)

    def persist_message(
        self,
        session_id: str,
        role: str,
        content: str,
        *,
        speaker_id: str | None = None,
        input_modality: str | None = None,
        output_modality: str | None = None,
        emotion_label: str | None = None,
        audio_ref: str | None = None,
    ) -> ChatMessage:
        now = _now()
        message_id = uuid.uuid4().hex
        with self.database.connect() as connection:
            row = connection.execute(
                "select coalesce(max(ordinal), -1) + 1 as ordinal from messages where session_id = ?",
                (session_id,),
            ).fetchone()
            ordinal = int(row["ordinal"])
            connection.execute(
                """
                insert into messages (
                  id, session_id, role, content, created_at, ordinal,
                  speaker_id, input_modality, output_modality, emotion_label, audio_ref
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message_id,
                    session_id,
                    role,
                    content,
                    now,
                    ordinal,
                    _clean_optional(speaker_id),
                    _clean_optional(input_modality),
                    _clean_optional(output_modality),
                    _clean_optional(emotion_label),
                    _clean_optional(audio_ref),
                ),
            )
            connection.execute(
                """
                update sessions
                set updated_at = ?, last_message_at = ?
                where id = ?
                """,
                (now, now, session_id),
            )
        return ChatMessage(
            message_id=message_id,
            role=role,
            content=content,
            speaker_id=_clean_optional(speaker_id),
            input_modality=_clean_optional(input_modality),
            output_modality=_clean_optional(output_modality),
            emotion_label=_clean_optional(emotion_label),
            audio_ref=_clean_optional(audio_ref),
        )

    def load_messages(self, session_id: str) -> list[ChatMessage]:
        rows = self.database.fetch_all(
            """
            select id, role, content, speaker_id, input_modality, output_modality, emotion_label, audio_ref
            from messages
            where session_id = ?
            order by ordinal
            """,
            (session_id,),
        )
        return [
            ChatMessage(
                message_id=str(row["id"]),
                role=str(row["role"]),
                content=str(row["content"]),
                speaker_id=str(row["speaker_id"]) if row["speaker_id"] is not None else None,
                input_modality=str(row["input_modality"]) if row["input_modality"] is not None else None,
                output_modality=str(row["output_modality"]) if row["output_modality"] is not None else None,
                emotion_label=str(row["emotion_label"]) if row["emotion_label"] is not None else None,
                audio_ref=str(row["audio_ref"]) if row["audio_ref"] is not None else None,
            )
            for row in rows
        ]

    def record_event(self, session_id: str, event_type: str, payload: dict[str, Any], *, created_at: str | None = None) -> None:
        self.database.execute(
            """
            insert into session_events (id, session_id, type, payload_json, created_at)
            values (?, ?, ?, ?, ?)
            """,
            (
                uuid.uuid4().hex,
                session_id,
                event_type,
                json.dumps(payload, ensure_ascii=False, sort_keys=True),
                created_at or _now(),
            ),
        )

    def load_events(self, session_id: str) -> list[dict[str, Any]]:
        rows = self.database.fetch_all(
            """
            select id, session_id, type, payload_json, created_at
            from session_events
            where session_id = ?
            order by created_at
            """,
            (session_id,),
        )
        return [
            {
                "eventId": str(row["id"]),
                "sessionId": str(row["session_id"]),
                "type": str(row["type"]),
                "payload": json.loads(str(row["payload_json"])),
                "createdAt": str(row["created_at"]),
            }
            for row in rows
        ]

    def _session_from_row(self, row: Any, *, include_history: bool) -> StoredSession:
        session_id = str(row["id"])
        return StoredSession(
            session_id=session_id,
            role_id=str(row["role_id"]),
            role_name=str(row["role_name"]),
            role_version=str(row["role_version"]),
            mode=str(row["mode"]),
            companion_id=str(row["companion_id"]),
            scenario_id=str(row["scenario_id"]) if row["scenario_id"] is not None else None,
            scenario_name=str(row["scenario_name"]) if row["scenario_name"] is not None else None,
            title=str(row["title"]) if row["title"] is not None else None,
            status=str(row["status"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
            last_message_at=str(row["last_message_at"]) if row["last_message_at"] is not None else None,
            history=self.load_messages(session_id) if include_history else [],
        )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None
