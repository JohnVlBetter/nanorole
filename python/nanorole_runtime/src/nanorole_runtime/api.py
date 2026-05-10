from __future__ import annotations

import json
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse, StreamingResponse
from pydantic import BaseModel

from .config import AppConfig
from .llm import ChatClient, OpenAICompatibleClient
from .roles import RolePackage, RoleValidationError
from .sessions import SessionManager, SessionNotFoundError


class CreateSessionRequest(BaseModel):
    role: dict[str, Any]


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
            role = RolePackage(**request.role)
        except (TypeError, ValueError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        session = manager.create_session(role)
        return {
            "sessionId": session.session_id,
            "roleId": role.id,
            "roleName": role.name,
            "opening": role.opening,
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

