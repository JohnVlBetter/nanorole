from __future__ import annotations

import json
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse, StreamingResponse
from pydantic import BaseModel

from .config import AppConfig
from .llm import ChatClient, OpenAICompatibleClient
from .roles import RoleNotFoundError
from .sessions import SessionManager, SessionNotFoundError


class CreateSessionRequest(BaseModel):
    role_id: str


class StreamMessageRequest(BaseModel):
    message: str


def create_app(config: AppConfig, client: ChatClient | None = None) -> FastAPI:
    app = FastAPI(title="Nanorole Runtime")
    manager = SessionManager(config=config, client=client or OpenAICompatibleClient())
    app.state.session_manager = manager

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "nanorole-runtime"}

    @app.post("/v1/sessions")
    def create_session(request: CreateSessionRequest) -> dict[str, str]:
        try:
            session = manager.create_session(request.role_id)
        except RoleNotFoundError as error:
            raise HTTPException(status_code=404, detail=f"role not found: {request.role_id}") from error
        except (TypeError, ValueError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return {
            "sessionId": session.session_id,
            "roleId": session.role_id,
            "roleName": session.role_name,
            "opening": session.role_opening,
        }

    @app.get("/v1/sessions")
    def list_sessions() -> dict[str, list[dict[str, str | None]]]:
        return {"sessions": [_session_summary(session) for session in manager.list_sessions()]}

    @app.get("/v1/sessions/{session_id}")
    def get_session(session_id: str) -> dict[str, str | None]:
        try:
            return _session_detail(manager.get_session(session_id))
        except SessionNotFoundError as error:
            raise HTTPException(status_code=404, detail=f"session not found: {session_id}") from error

    @app.get("/v1/sessions/{session_id}/messages")
    def get_messages(session_id: str) -> dict[str, list[dict[str, str | None]]]:
        try:
            session = manager.get_session(session_id)
        except SessionNotFoundError as error:
            raise HTTPException(status_code=404, detail=f"session not found: {session_id}") from error
        return {
            "messages": [
                {"messageId": message.message_id, "role": message.role, "content": message.content}
                for message in session.history
            ]
        }

    @app.post("/v1/sessions/{session_id}/messages:stream")
    async def stream_message(session_id: str, request: StreamMessageRequest) -> StreamingResponse:
        async def events():
            try:
                async for event in manager.stream_message(session_id, request.message):
                    yield _sse(event.type, event.data)
            except SessionNotFoundError as error:
                yield _sse("error", {"message": f"session not found: {session_id}"})

        return StreamingResponse(events(), media_type="text/event-stream")

    @app.get("/v1/sessions/{session_id}/export")
    def export_session(session_id: str) -> PlainTextResponse:
        try:
            return PlainTextResponse(manager.export_session(session_id), media_type="application/jsonl")
        except SessionNotFoundError as error:
            raise HTTPException(status_code=404, detail=f"session not found: {session_id}") from error

    return app


def _sse(event_type: str, data: dict[str, Any]) -> str:
    return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _session_summary(session) -> dict[str, str | None]:
    return {
        "sessionId": session.session_id,
        "roleId": session.role_id,
        "roleName": session.role_name,
        "createdAt": session.created_at,
        "updatedAt": session.updated_at,
        "lastMessageAt": session.last_message_at,
    }


def _session_detail(session) -> dict[str, str | None]:
    return {
        **_session_summary(session),
        "roleVersion": session.role_version,
        "opening": session.role_opening,
        "status": session.status,
    }
