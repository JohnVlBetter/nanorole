from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, AsyncIterator

from .config import AppConfig, redact_secrets
from .context import ContextAssembler
from .llm import ChatClient
from .memory import MemoryStore
from .roles import RolePackage, load_role_by_id
from .sessions_types import ChatMessage
from .storage import Database


DEFAULT_USER_ID = "local-user"


@dataclass
class RuntimeEvent:
    type: str
    data: dict[str, Any]
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_jsonl(self) -> str:
        return json.dumps(
            {"ts": self.timestamp, "type": self.type, **self.data},
            ensure_ascii=False,
            sort_keys=True,
        )


@dataclass
class StreamEvent:
    type: str
    data: dict[str, Any]


@dataclass
class SessionState:
    session_id: str
    role_id: str
    role_name: str
    role_version: str
    role_opening: str
    config: AppConfig
    created_at: str | None = None
    updated_at: str | None = None
    last_message_at: str | None = None
    status: str = "active"
    history: list[ChatMessage] = field(default_factory=list)
    events: list[RuntimeEvent] = field(default_factory=list)


class SessionNotFoundError(KeyError):
    pass


class SessionManager:
    def __init__(self, *, config: AppConfig, client: ChatClient) -> None:
        self.config = config
        self.client = client
        self.database = Database(config.paths.database_path)
        self.database.initialize()
        self._role_cache: dict[str, RolePackage] = {}
        self._sessions: dict[str, SessionState] = {}

    def create_session(self, role_id: str, config: AppConfig | None = None) -> SessionState:
        role = self._resolve_role(role_id)
        now = self._now()
        session = SessionState(
            session_id=uuid.uuid4().hex,
            role_id=role.id,
            role_name=role.name,
            role_version=role.version,
            role_opening=role.opening,
            config=config or self.config,
            created_at=now,
            updated_at=now,
            last_message_at=None,
        )
        self._persist_session(session, role, now)
        self._record(
            session,
            "session_started",
            {
                "session_id": session.session_id,
                "role_id": session.role_id,
                "role_name": session.role_name,
                "role_version": session.role_version,
                "model": session.config.model.name,
                "config": redact_secrets(
                    {
                        "model": {
                            "provider": session.config.model.provider,
                            "base_url": session.config.model.base_url,
                            "name": session.config.model.name,
                            "api_key": session.config.model.api_key,
                        }
                    }
                ),
            },
        )
        self._sessions[session.session_id] = session
        self._write_log(
            "session_created",
            {
                "session_id": session.session_id,
                "role_id": role.id,
                "role_name": role.name,
                "model": session.config.model.name,
            },
        )
        return session

    def get_session(self, session_id: str) -> SessionState:
        if session_id in self._sessions:
            return self._sessions[session_id]
        session = self._load_session(session_id)
        self._sessions[session.session_id] = session
        return session

    def list_sessions(self) -> list[SessionState]:
        rows = self.database.fetch_all(
            """
            select *
            from sessions
            where status != 'deleted'
            order by coalesce(last_message_at, created_at) desc, created_at desc
            """
        )
        return [self._state_from_session_row(row, include_history=True) for row in rows]

    async def stream_message(self, session_id: str, message: str) -> AsyncIterator[StreamEvent]:
        session = self.get_session(session_id)
        role = self._resolve_role(session.role_id)
        user_message = self._persist_message(session.session_id, "user", message)
        session.history.append(user_message)
        self._record(session, "user_message", {"session_id": session_id, "role_id": session.role_id, "content": message})

        assistant_parts: list[str] = []
        messages: list[dict[str, str]] = []
        started = time.perf_counter()
        first_chunk_latency_ms: float | None = None
        first_token_latency_ms: float | None = None
        try:
            memory_store = MemoryStore(self.database)
            assembler = ContextAssembler(memory_store=memory_store)
            messages, used_memories = assembler.build_messages(
                role=role,
                user_id=DEFAULT_USER_ID,
                companion_id=role.id,
                history=session.history[:-1],
                user_input=message,
            )
            used_memory_ids = [memory.memory_id for memory in used_memories]
            memory_store.mark_used(used_memory_ids)
            self._record(
                session,
                "memory_retrieval",
                {"session_id": session_id, "role_id": session.role_id, "memory_ids": used_memory_ids},
            )
            if session.config.logging.trace_requests:
                self._write_log(
                    "trace_request",
                    {
                        "session_id": session_id,
                        "role_id": session.role_id,
                        "messages": messages,
                        "model": session.config.model.name,
                    },
                )

            def set_first_chunk_latency(latency_ms: float) -> None:
                nonlocal first_chunk_latency_ms
                if first_chunk_latency_ms is None:
                    first_chunk_latency_ms = round(latency_ms, 3)

            def set_first_token_latency(latency_ms: float) -> None:
                nonlocal first_token_latency_ms
                if first_token_latency_ms is None:
                    first_token_latency_ms = round(latency_ms, 3)

            async for chunk in self.client.stream_chat(
                messages=messages,
                config=session.config,
                role=role,
                on_first_chunk=set_first_chunk_latency,
                on_first_token=set_first_token_latency,
            ):
                assistant_parts.append(chunk)
                self._record(session, "assistant_delta", {"session_id": session_id, "role_id": session.role_id, "delta": chunk})
                yield StreamEvent("token", {"delta": chunk})

            assistant_message = "".join(assistant_parts)
            session.history.append(self._persist_message(session.session_id, "assistant", assistant_message))
            self._record(session, "assistant_message", {"session_id": session_id, "role_id": session.role_id, "content": assistant_message})
            self._write_log(
                "request_completed",
                {
                    "session_id": session_id,
                    "role_id": session.role_id,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 3),
                    "first_chunk_latency_ms": first_chunk_latency_ms,
                    "first_token_latency_ms": first_token_latency_ms,
                    "token_count": len(assistant_parts),
                    "input": {
                        "user_message": message,
                        "messages": messages,
                    },
                    "output": {
                        "message": assistant_message,
                        "chunks": assistant_parts,
                    },
                    "error": None,
                },
            )
            yield StreamEvent("final", {"message": assistant_message})
        except Exception as error:
            self._record(session, "error", {"session_id": session_id, "role_id": session.role_id, "message": str(error)})
            self._write_log(
                "request_failed",
                {
                    "session_id": session_id,
                    "role_id": session.role_id,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 3),
                    "first_chunk_latency_ms": first_chunk_latency_ms,
                    "first_token_latency_ms": first_token_latency_ms,
                    "token_count": len(assistant_parts),
                    "input": {
                        "user_message": message,
                        "messages": messages,
                    },
                    "output": {
                        "message": "".join(assistant_parts),
                        "chunks": assistant_parts,
                    },
                    "error": str(error),
                },
            )
            yield StreamEvent("error", {"message": str(error)})

    def export_session(self, session_id: str) -> str:
        session = self.get_session(session_id)
        exported = "\n".join(event.to_jsonl() for event in session.events) + "\n"
        session.config.paths.sessions_dir.mkdir(parents=True, exist_ok=True)
        (session.config.paths.sessions_dir / f"{session_id}.jsonl").write_text(exported, encoding="utf-8")
        return exported

    def _record(self, session: SessionState, event_type: str, data: dict[str, Any]) -> None:
        event = RuntimeEvent(event_type, data)
        session.events.append(event)
        with self.database.connect() as connection:
            connection.execute(
                """
                insert into session_events (id, session_id, type, payload_json, created_at)
                values (?, ?, ?, ?, ?)
                """,
                (
                    uuid.uuid4().hex,
                    session.session_id,
                    event_type,
                    json.dumps(redact_secrets(data), ensure_ascii=False, sort_keys=True),
                    event.timestamp,
                ),
            )

    def _resolve_role(self, role_id: str) -> RolePackage:
        if role_id in self._role_cache:
            return self._role_cache[role_id]
        role = load_role_by_id(self.config.paths.roles_dir, role_id)
        self._role_cache[role.id] = role
        return role

    def _write_log(self, event_type: str, data: dict[str, Any]) -> None:
        self.config.paths.logs_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "type": event_type,
            **redact_secrets(data),
        }
        line = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        with (self.config.paths.logs_dir / "runtime.jsonl").open("a", encoding="utf-8") as file:
            file.write(f"{line}\n")

    def _persist_session(self, session: SessionState, role: RolePackage, now: str) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """
                insert into users (id, display_name, created_at, updated_at)
                values (?, ?, ?, ?)
                on conflict(id) do update set updated_at = excluded.updated_at
                """,
                (DEFAULT_USER_ID, "Local User", now, now),
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
                (role.id, role.id, role.version, role.name, now, now),
            )
            connection.execute(
                """
                insert into sessions (
                  id, user_id, companion_id, role_id, role_name, role_version, title, status,
                  created_at, updated_at, last_message_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session.session_id,
                    DEFAULT_USER_ID,
                    role.id,
                    role.id,
                    role.name,
                    role.version,
                    None,
                    "active",
                    now,
                    now,
                    None,
                ),
            )

    def _persist_message(self, session_id: str, role: str, content: str) -> ChatMessage:
        now = self._now()
        message_id = uuid.uuid4().hex
        with self.database.connect() as connection:
            row = connection.execute(
                "select coalesce(max(ordinal), -1) + 1 as ordinal from messages where session_id = ?",
                (session_id,),
            ).fetchone()
            ordinal = int(row["ordinal"])
            connection.execute(
                """
                insert into messages (id, session_id, role, content, created_at, ordinal)
                values (?, ?, ?, ?, ?, ?)
                """,
                (message_id, session_id, role, content, now, ordinal),
            )
            connection.execute(
                """
                update sessions
                set updated_at = ?, last_message_at = ?
                where id = ?
                """,
                (now, now, session_id),
            )
        if session_id in self._sessions:
            self._sessions[session_id].updated_at = now
            self._sessions[session_id].last_message_at = now
        return ChatMessage(role=role, content=content, message_id=message_id)

    def _load_session(self, session_id: str) -> SessionState:
        row = self.database.fetch_one("select * from sessions where id = ? and status != 'deleted'", (session_id,))
        if row is None:
            raise SessionNotFoundError(session_id)
        return self._state_from_session_row(row, include_history=True)

    def _state_from_session_row(self, row: Any, *, include_history: bool) -> SessionState:
        try:
            role = self._resolve_role(str(row["role_id"]))
            opening = role.opening
        except Exception:
            opening = ""
        history = self._load_messages(str(row["id"])) if include_history else []
        return SessionState(
            session_id=str(row["id"]),
            role_id=str(row["role_id"]),
            role_name=str(row["role_name"]),
            role_version=str(row["role_version"]),
            role_opening=opening,
            config=self.config,
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
            last_message_at=str(row["last_message_at"]) if row["last_message_at"] is not None else None,
            status=str(row["status"]),
            history=history,
        )

    def _load_messages(self, session_id: str) -> list[ChatMessage]:
        rows = self.database.fetch_all(
            """
            select id, role, content
            from messages
            where session_id = ?
            order by ordinal
            """,
            (session_id,),
        )
        return [
            ChatMessage(message_id=str(row["id"]), role=str(row["role"]), content=str(row["content"]))
            for row in rows
        ]

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()


__all__ = [
    "ChatMessage",
    "RuntimeEvent",
    "SessionManager",
    "SessionNotFoundError",
    "SessionState",
    "StreamEvent",
]
