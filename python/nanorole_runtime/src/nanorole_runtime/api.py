from __future__ import annotations

import json
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse, StreamingResponse
from pydantic import BaseModel

from .config import AppConfig
from .llm import ChatClient, OpenAICompatibleClient
from .memory import MemoryRecord, MemoryStore
from .roles import RoleNotFoundError
from .sessions import DEFAULT_USER_ID, SessionManager, SessionNotFoundError


class CreateSessionRequest(BaseModel):
    role_id: str


class StreamMessageRequest(BaseModel):
    message: str


class UpdateSessionRequest(BaseModel):
    title: str | None = None
    status: str | None = None


class CreateMemoryRequest(BaseModel):
    userId: str = DEFAULT_USER_ID
    companionId: str
    type: str
    content: str
    importance: float
    confidence: float
    sourceMessageIds: list[str] = []


class UpdateMemoryRequest(BaseModel):
    type: str | None = None
    content: str | None = None
    importance: float | None = None
    confidence: float | None = None
    status: str | None = None
    sourceMessageIds: list[str] | None = None


def create_app(config: AppConfig, client: ChatClient | None = None) -> FastAPI:
    app = FastAPI(title="Nanorole Runtime")
    manager = SessionManager(config=config, client=client or OpenAICompatibleClient())
    memory_store = MemoryStore(manager.database)
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

    @app.patch("/v1/sessions/{session_id}")
    def update_session(session_id: str, request: UpdateSessionRequest) -> dict[str, str | None]:
        try:
            return _session_detail(manager.update_session(session_id, title=request.title, status=request.status))
        except SessionNotFoundError as error:
            raise HTTPException(status_code=404, detail=f"session not found: {session_id}") from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

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

    @app.get("/v1/sessions/{session_id}/context-preview")
    def context_preview(session_id: str, userInput: str = "") -> dict[str, object]:
        try:
            return manager.preview_context(session_id, user_input=userInput)
        except SessionNotFoundError as error:
            raise HTTPException(status_code=404, detail=f"session not found: {session_id}") from error

    @app.get("/v1/memories")
    def list_memories(userId: str = DEFAULT_USER_ID, companionId: str = "") -> dict[str, list[dict[str, object]]]:
        if not companionId:
            raise HTTPException(status_code=400, detail="companionId is required")
        try:
            memories = memory_store.list_memories(user_id=userId, companion_id=companionId)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return {"memories": [_memory_response(memory, memory_store) for memory in memories]}

    @app.post("/v1/memories")
    def create_memory(request: CreateMemoryRequest) -> dict[str, object]:
        try:
            memory = memory_store.create_memory(
                user_id=request.userId,
                companion_id=request.companionId,
                memory_type=request.type,
                content=request.content,
                importance=request.importance,
                confidence=request.confidence,
                source_message_ids=request.sourceMessageIds,
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return _memory_response(memory, memory_store)

    @app.patch("/v1/memories/{memory_id}")
    def update_memory(memory_id: str, request: UpdateMemoryRequest) -> dict[str, object]:
        try:
            memory = memory_store.update_memory(
                memory_id,
                memory_type=request.type,
                content=request.content,
                importance=request.importance,
                confidence=request.confidence,
                status=request.status,
                source_message_ids=request.sourceMessageIds,
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail=f"memory not found: {memory_id}") from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return _memory_response(memory, memory_store)

    @app.delete("/v1/memories/{memory_id}")
    def delete_memory(memory_id: str) -> dict[str, object]:
        try:
            memory = memory_store.delete_memory(memory_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=f"memory not found: {memory_id}") from error
        return _memory_response(memory, memory_store)

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
        "title": session.title,
        "status": session.status,
        "createdAt": session.created_at,
        "updatedAt": session.updated_at,
        "lastMessageAt": session.last_message_at,
    }


def _session_detail(session) -> dict[str, str | None]:
    return {
        **_session_summary(session),
        "roleVersion": session.role_version,
        "opening": session.role_opening,
    }


def _memory_response(memory: MemoryRecord, memory_store: MemoryStore) -> dict[str, object]:
    return {
        "memoryId": memory.memory_id,
        "userId": memory.user_id,
        "companionId": memory.companion_id,
        "type": memory.type,
        "content": memory.content,
        "importance": memory.importance,
        "confidence": memory.confidence,
        "status": memory.status,
        "createdAt": memory.created_at,
        "updatedAt": memory.updated_at,
        "lastUsedAt": memory.last_used_at,
        "useCount": memory.use_count,
        "sourceMessageIds": memory.source_message_ids,
        "sourceMessages": [
            {
                "messageId": source.message_id,
                "role": source.role,
                "content": source.content,
            }
            for source in memory_store.get_source_messages(memory.memory_id)
        ],
    }
