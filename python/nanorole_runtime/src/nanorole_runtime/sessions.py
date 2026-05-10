from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, AsyncIterator

from .config import AppConfig, redact_secrets
from .llm import ChatClient
from .prompt import build_messages
from .roles import RolePackage
from .sessions_types import ChatMessage


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
    role: RolePackage
    config: AppConfig
    history: list[ChatMessage] = field(default_factory=list)
    events: list[RuntimeEvent] = field(default_factory=list)


class SessionNotFoundError(KeyError):
    pass


class SessionManager:
    def __init__(self, *, config: AppConfig, client: ChatClient) -> None:
        self.config = config
        self.client = client
        self._sessions: dict[str, SessionState] = {}

    def create_session(self, role: RolePackage, config: AppConfig | None = None) -> SessionState:
        session = SessionState(
            session_id=uuid.uuid4().hex,
            role=role,
            config=config or self.config,
        )
        self._record(
            session,
            "session_started",
            {
                "session_id": session.session_id,
                "role_id": role.id,
                "role_name": role.name,
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
        try:
            return self._sessions[session_id]
        except KeyError as error:
            raise SessionNotFoundError(session_id) from error

    async def stream_message(self, session_id: str, message: str) -> AsyncIterator[StreamEvent]:
        session = self.get_session(session_id)
        session.history.append(ChatMessage(role="user", content=message))
        self._record(session, "user_message", {"session_id": session_id, "content": message})

        assistant_parts: list[str] = []
        started = time.perf_counter()
        try:
            messages = build_messages(session.role, session.history[:-1], message)
            if session.config.logging.trace_requests:
                self._write_log(
                    "trace_request",
                    {
                        "session_id": session_id,
                        "messages": messages,
                        "model": session.config.model.name,
                    },
                )
            async for chunk in self.client.stream_chat(messages=messages, config=session.config, role=session.role):
                assistant_parts.append(chunk)
                self._record(session, "assistant_delta", {"session_id": session_id, "delta": chunk})
                yield StreamEvent("token", {"delta": chunk})

            assistant_message = "".join(assistant_parts)
            session.history.append(ChatMessage(role="assistant", content=assistant_message))
            self._record(session, "assistant_message", {"session_id": session_id, "content": assistant_message})
            self._write_log(
                "request_completed",
                {
                    "session_id": session_id,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 3),
                    "token_count": len(assistant_parts),
                    "error": None,
                },
            )
            yield StreamEvent("final", {"message": assistant_message})
        except Exception as error:
            self._record(session, "error", {"session_id": session_id, "message": str(error)})
            self._write_log(
                "request_failed",
                {
                    "session_id": session_id,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 3),
                    "token_count": len(assistant_parts),
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
        session.events.append(RuntimeEvent(event_type, data))

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


__all__ = [
    "ChatMessage",
    "RuntimeEvent",
    "SessionManager",
    "SessionNotFoundError",
    "SessionState",
    "StreamEvent",
]
