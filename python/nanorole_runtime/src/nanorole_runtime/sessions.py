from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, AsyncIterator

from .config import AppConfig, redact_secrets
from .context import ContextAssembler
from .llm import ChatClient
from .memory import MemoryExtractor, MemoryRecord, MemoryStore, RelationshipState
from .roles import RolePackage, load_role_by_id
from .scenarios import load_scenario_by_id
from .session_store import SessionStore, StoredSession
from .sessions_types import ChatMessage
from .storage import Database
from .story import StoryService
from .summaries import SummaryStore, generate_session_summary, should_update_summary
from .turns import CompanionTurnPipeline


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
    mode: str = "companion"
    scenario_id: str | None = None
    scenario_name: str | None = None
    participants: list[dict[str, Any]] = field(default_factory=list)
    title: str | None = None
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
        self.session_store = SessionStore(self.database)
        self.story_service = StoryService(self.database)
        self._role_cache: dict[str, RolePackage] = {}
        self._sessions: dict[str, SessionState] = {}

    def create_session(self, role_id: str, config: AppConfig | None = None) -> SessionState:
        role = self._resolve_role(role_id)
        stored = self.session_store.create_session(
            user_id=DEFAULT_USER_ID,
            companion_id=role.id,
            role_id=role.id,
            role_name=role.name,
            role_version=role.version,
            mode="companion",
            scenario_id=None,
            scenario_name=None,
        )
        session = self._state_from_stored_session(stored, role_opening=role.opening, config=config or self.config)
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

    def create_scenario_session(self, scenario_id: str, role_ids: list[str] | None = None) -> SessionState:
        scenario = load_scenario_by_id(self.config.paths.scenarios_dir, scenario_id)
        selected_role_ids = role_ids if role_ids is not None else scenario.roles
        if not selected_role_ids:
            raise ValueError("scenario session requires at least one role")
        roles = [self._resolve_role(role_id) for role_id in selected_role_ids]
        active_role = roles[0]
        stored = self.session_store.create_session(
            user_id=DEFAULT_USER_ID,
            companion_id=active_role.id,
            role_id=active_role.id,
            role_name=active_role.name,
            role_version=active_role.version,
            mode="scenario",
            scenario_id=scenario.id,
            scenario_name=scenario.name,
        )
        session = self._state_from_stored_session(
            stored,
            role_opening=scenario.initial_scene,
            config=self.config,
            participants=[
                {"roleId": role.id, "displayName": role.name, "ordinal": index, "status": "active", "visibility": {}}
                for index, role in enumerate(roles)
            ],
        )
        self._persist_session_participants(session.session_id, roles)
        self.story_service.create_story_state(session.session_id, scenario)
        self._record(
            session,
            "scenario_session_started",
            {
                "session_id": session.session_id,
                "scenario_id": scenario.id,
                "scenario_name": scenario.name,
                "role_ids": selected_role_ids,
            },
        )
        self._sessions[session.session_id] = session
        self._write_log(
            "scenario_session_created",
            {
                "session_id": session.session_id,
                "scenario_id": scenario.id,
                "role_ids": selected_role_ids,
            },
        )
        return session

    def get_session(self, session_id: str) -> SessionState:
        if session_id in self._sessions:
            return self._sessions[session_id]
        session = self._load_session(session_id)
        self._sessions[session.session_id] = session
        return session

    def get_story_state(self, session_id: str) -> dict[str, Any]:
        self.get_session(session_id)
        try:
            return self.story_service.get_state(session_id)
        except KeyError as error:
            raise SessionNotFoundError(session_id) from error

    def append_story_event(self, session_id: str, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        session = self.get_session(session_id)
        try:
            event = self.story_service.append_event(session_id, event_type, payload)
        except KeyError as error:
            raise SessionNotFoundError(session_id) from error
        self._record(
            session,
            "scene_event",
            {
                "session_id": session_id,
                "event_id": event["eventId"],
                "event_type": event["type"],
                "ordinal": event["ordinal"],
            },
        )
        return event

    def list_sessions(self) -> list[SessionState]:
        return [self._state_from_stored_session(session) for session in self.session_store.list_sessions()]

    def preview_context(self, session_id: str, user_input: str = "") -> dict[str, object]:
        session = self.get_session(session_id)
        role = self._resolve_role(session.role_id)
        memory_store = MemoryStore(self.database)
        assembler = ContextAssembler(memory_store=memory_store)
        story_context = self._visible_story_context(session.session_id) if session.mode == "scenario" else None
        package = assembler.build_context_package(
            session_id=session.session_id,
            mode="story" if story_context else session.mode,
            role=role,
            user_id=DEFAULT_USER_ID,
            companion_id=role.id,
            history=session.history,
            user_input=user_input,
            session_summary=self._session_summary_text(session.session_id),
            story_context=story_context,
        )
        return {
            "sessionId": session.session_id,
            "mode": session.mode,
            "messages": package.model_messages,
            "systemPrompt": package.model_messages[0]["content"],
            "context": {
                "world": package.world_context,
                "relationship": _relationship_response(package.relationship),
                "selectedMemories": [_memory_context_response(memory) for memory in package.selected_memories],
                "sessionSummary": package.session_summary,
                "story": package.story,
            },
            "usedMemories": [
                {
                    "memoryId": memory.memory_id,
                    "type": memory.type,
                    "content": memory.content,
                    "importance": memory.importance,
                    "confidence": memory.confidence,
                }
                for memory in package.selected_memories
            ],
            "usedStory": package.story,
        }

    async def stream_message(
        self,
        session_id: str,
        message: str,
        *,
        speaker_id: str | None = None,
        input_modality: str | None = "text",
        emotion_label: str | None = None,
        audio_ref: str | None = None,
    ) -> AsyncIterator[StreamEvent]:
        session = self.get_session(session_id)
        if session.mode == "scenario":
            async for event in self._stream_scenario_message(
                session=session,
                message=message,
                speaker_id=speaker_id,
                input_modality=input_modality,
                emotion_label=emotion_label,
                audio_ref=audio_ref,
            ):
                yield event
            return

        role = self._resolve_role(session.role_id)
        pipeline = CompanionTurnPipeline(
            session_id=session.session_id,
            role=role,
            config=session.config,
            client=self.client,
            history=session.history,
            user_id=DEFAULT_USER_ID,
            companion_id=role.id,
            session_summary=self._session_summary_text(session.session_id),
            story_context=self._visible_story_context(session.session_id) if session.mode == "scenario" else None,
            memory_store=MemoryStore(self.database),
            persist_message=lambda message_role, content, **metadata: self._persist_message(
                session.session_id,
                message_role,
                content,
                **metadata,
            ),
            record_event=lambda event_type, data: self._record(session, event_type, data),
            write_log=self._write_log,
            schedule_memory_extraction=lambda **kwargs: self._schedule_memory_extraction(session=session, role=role, **kwargs),
            schedule_summary_update=lambda: self._schedule_summary_update(session=session),
        )
        async for event in pipeline.stream(
            user_input=message,
            speaker_id=speaker_id,
            input_modality=input_modality,
            emotion_label=emotion_label,
            audio_ref=audio_ref,
        ):
            yield StreamEvent(event.type, event.data)

    async def _stream_scenario_message(
        self,
        *,
        session: SessionState,
        message: str,
        speaker_id: str | None,
        input_modality: str | None,
        emotion_label: str | None,
        audio_ref: str | None,
    ) -> AsyncIterator[StreamEvent]:
        started = datetime.now(timezone.utc)
        history_before_turn = list(session.history)
        self._record(
            session,
            "turn_started",
            {
                "session_id": session.session_id,
                "mode": "scenario",
                "speaker_id": speaker_id or "user",
                "input_modality": input_modality or "text",
            },
        )
        user_message = self._persist_message(
            session.session_id,
            "user",
            message,
            speaker_id=speaker_id or "user",
            input_modality=input_modality or "text",
            emotion_label=emotion_label,
            audio_ref=audio_ref,
        )
        session.history.append(user_message)
        self._record(
            session,
            "user_message",
            {
                "session_id": session.session_id,
                "message_id": user_message.message_id,
                "speaker_id": user_message.speaker_id,
                "input_modality": user_message.input_modality,
                "emotion_label": user_message.emotion_label,
                "audio_ref": user_message.audio_ref,
                "content": message,
            },
        )

        decisions, director_fallback = await self._direct_scenario_responses(session=session, user_input=message)
        self._record(
            session,
            "director_decision",
            {"session_id": session.session_id, "responses": decisions, "fallback": director_fallback},
        )
        yield StreamEvent("director", {"responses": decisions, "fallback": director_fallback})

        assistant_messages: list[ChatMessage] = []
        used_memory_ids: list[str] = []
        try:
            for decision in decisions:
                role = self._resolve_role(str(decision["speakerId"]))
                memory_store = MemoryStore(self.database)
                assembler = ContextAssembler(memory_store=memory_store)
                story_context = self._visible_story_context(session.session_id, speaker_id=role.id)
                session_summary = self._session_summary_text(session.session_id)
                messages, used_memories = assembler.build_messages(
                    role=role,
                    user_id=DEFAULT_USER_ID,
                    companion_id=role.id,
                    history=history_before_turn,
                    user_input=message,
                    session_summary=session_summary,
                    story_context=story_context,
                )
                goal = str(decision.get("goal") or "").strip()
                if goal:
                    messages[0]["content"] += f"\n\nDirector instruction for this response:\n{goal}\n"
                role_memory_ids = [memory.memory_id for memory in used_memories]
                used_memory_ids.extend(role_memory_ids)
                memory_store.mark_used(role_memory_ids)
                self._record(
                    session,
                    "memory_retrieval",
                    {"session_id": session.session_id, "role_id": role.id, "memory_ids": role_memory_ids},
                )
                self._record(
                    session,
                    "context_built",
                    {
                        "session_id": session.session_id,
                        "role_id": role.id,
                        "speaker_id": role.id,
                        "message_count": len(messages),
                        "used_memory_ids": role_memory_ids,
                        "system_prompt_chars": len(messages[0]["content"]) if messages else 0,
                        "history_messages": max(len(messages) - 2, 0),
                        "has_session_summary": bool(session_summary and session_summary.strip()),
                        "used_story": {
                            "public_fact_count": len(story_context.get("publicFacts", [])),
                            "revealed_clue_count": len(story_context.get("revealedClues", [])),
                            "recent_event_count": len(story_context.get("recentEvents", [])),
                            "visible_hidden_fact_count": len(story_context.get("visibleHiddenFacts", [])),
                        },
                    },
                )

                assistant_parts: list[str] = []
                async for chunk in self.client.stream_chat(messages=messages, config=session.config, role=role):
                    assistant_parts.append(chunk)
                    self._record(
                        session,
                        "assistant_delta",
                        {"session_id": session.session_id, "role_id": role.id, "speaker_id": role.id, "delta": chunk},
                    )
                    yield StreamEvent("token", {"delta": chunk, "speakerId": role.id})

                assistant_text = "".join(assistant_parts)
                assistant_message = self._persist_message(
                    session.session_id,
                    "assistant",
                    assistant_text,
                    speaker_id=role.id,
                    output_modality="text",
                )
                session.history.append(assistant_message)
                assistant_messages.append(assistant_message)
                self._record(
                    session,
                    "assistant_message",
                    {
                        "session_id": session.session_id,
                        "role_id": role.id,
                        "message_id": assistant_message.message_id,
                        "speaker_id": assistant_message.speaker_id,
                        "output_modality": assistant_message.output_modality,
                        "content": assistant_text,
                    },
                )
                yield StreamEvent(
                    "final",
                    {
                        "message": assistant_text,
                        "speakerId": role.id,
                        "messages": [_chat_message_response(item) for item in assistant_messages],
                    },
                )

            duration_ms = (datetime.now(timezone.utc) - started).total_seconds() * 1000
            self._record(
                session,
                "turn_completed",
                {
                    "session_id": session.session_id,
                    "mode": "scenario",
                    "input_message_id": user_message.message_id,
                    "output_message_ids": [item.message_id for item in assistant_messages],
                    "duration_ms": round(duration_ms, 3),
                    "used_memory_ids": used_memory_ids,
                },
            )
        except Exception as error:
            self._record(session, "error", {"session_id": session.session_id, "mode": "scenario", "message": str(error)})
            yield StreamEvent("error", {"message": str(error)})

    async def _direct_scenario_responses(self, *, session: SessionState, user_input: str) -> tuple[list[dict[str, str]], bool]:
        active_participants = [
            participant
            for participant in session.participants
            if str(participant.get("status") or "active") == "active"
        ]
        fallback = [
            {
                "speakerId": str((active_participants[0] if active_participants else {"roleId": session.role_id})["roleId"]),
                "goal": "Reply to the user while staying within the visible scenario context.",
            }
        ]
        participant_lines = "\n".join(
            f"- {participant['roleId']}: {participant['displayName']}"
            for participant in active_participants
        )
        try:
            decision = await self.client.complete_json(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are the Nanorole scenario director.\n"
                            "Choose one or two active participants to reply to the user's latest input.\n"
                            "Return JSON only: {\"responses\":[{\"speakerId\":\"role-id\",\"goal\":\"short goal\"}]}.\n"
                            "Do not select more than two participants."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Scenario: {session.scenario_name or session.scenario_id}\n"
                            f"Active participants:\n{participant_lines}\n\n"
                            f"User input: {user_input}"
                        ),
                    },
                ],
                config=session.config,
            )
        except Exception as error:
            self._record(
                session,
                "director_failed",
                {"session_id": session.session_id, "message": str(error), "fallback_speaker_id": fallback[0]["speakerId"]},
            )
            return fallback, True

        allowed = {str(participant["roleId"]) for participant in active_participants}
        responses = decision.get("responses")
        if not isinstance(responses, list):
            return fallback, True
        selected: list[dict[str, str]] = []
        seen: set[str] = set()
        for item in responses:
            if not isinstance(item, dict):
                continue
            speaker_id = str(item.get("speakerId") or "").strip()
            if speaker_id not in allowed or speaker_id in seen:
                continue
            goal = str(item.get("goal") or "").strip() or "Reply to the user."
            selected.append({"speakerId": speaker_id, "goal": goal})
            seen.add(speaker_id)
            if len(selected) == 2:
                break
        if not selected:
            return fallback, True
        return selected, False

    def export_session(self, session_id: str) -> str:
        session = self.get_session(session_id)
        exported = "\n".join(event.to_jsonl() for event in session.events) + "\n"
        session.config.paths.sessions_dir.mkdir(parents=True, exist_ok=True)
        (session.config.paths.sessions_dir / f"{session_id}.jsonl").write_text(exported, encoding="utf-8")
        return exported

    def update_session(
        self,
        session_id: str,
        *,
        title: str | None = None,
        status: str | None = None,
    ) -> SessionState:
        try:
            current = self.get_session(session_id)
            next_title = title.strip() or None if title is not None else current.title
            stored = self.session_store.update_session(session_id, title=next_title, status=status)
        except KeyError as error:
            raise SessionNotFoundError(session_id) from error
        session = self._state_from_stored_session(stored)
        if stored.status == "deleted":
            self._sessions.pop(session_id, None)
        else:
            self._sessions[session_id] = session
        return session

    def _record(self, session: SessionState, event_type: str, data: dict[str, Any]) -> None:
        event = RuntimeEvent(event_type, data)
        session.events.append(event)
        self.session_store.record_event(
            session.session_id,
            event_type,
            redact_secrets(data),
            created_at=event.timestamp,
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

    def _schedule_memory_extraction(
        self,
        *,
        session: SessionState,
        role: RolePackage,
        user_message: ChatMessage,
        user_text: str,
        assistant_message: ChatMessage,
        assistant_text: str,
    ) -> None:
        task = asyncio.create_task(
            self._extract_memory_after_turn(
                session=session,
                role=role,
                user_message=user_message,
                user_text=user_text,
                assistant_message=assistant_message,
                assistant_text=assistant_text,
            )
        )
        task.add_done_callback(self._consume_background_task_exception)

    def _schedule_summary_update(self, *, session: SessionState) -> None:
        task = asyncio.create_task(self._update_summary_after_turn(session=session))
        task.add_done_callback(self._consume_background_task_exception)

    def _consume_background_task_exception(self, task: asyncio.Task[None]) -> None:
        try:
            task.exception()
        except asyncio.CancelledError:
            pass

    async def _extract_memory_after_turn(
        self,
        *,
        session: SessionState,
        role: RolePackage,
        user_message: ChatMessage,
        user_text: str,
        assistant_message: ChatMessage,
        assistant_text: str,
    ) -> None:
        memory_store = MemoryStore(self.database)
        try:
            extractor = MemoryExtractor(client=self.client, config=session.config, store=memory_store)
            extraction = await extractor.extract_after_turn(
                user_id=DEFAULT_USER_ID,
                companion_id=role.id,
                user_message_id=user_message.message_id or "",
                user_message=user_text,
                assistant_message_id=assistant_message.message_id or "",
                assistant_message=assistant_text,
            )
            written = memory_store.apply_extraction(
                user_id=DEFAULT_USER_ID,
                companion_id=role.id,
                extraction=extraction,
            )
            self._record(
                session,
                "memory_extraction",
                {
                    "session_id": session.session_id,
                    "role_id": session.role_id,
                    "memory_ids": [memory.memory_id for memory in written],
                    "archived_memory_ids": extraction.archive_memory_ids,
                },
            )
        except Exception as extraction_error:
            self._record(
                session,
                "memory_extraction_failed",
                {"session_id": session.session_id, "role_id": session.role_id, "message": str(extraction_error)},
            )

    async def _update_summary_after_turn(self, *, session: SessionState) -> None:
        store = SummaryStore(self.database)
        try:
            history = self._load_messages(session.session_id)
            existing = store.get_latest_summary(session.session_id)
            covered_count = store.get_covered_message_count(session.session_id)
            if not should_update_summary(history, covered_count):
                return
            new_messages = history[covered_count:]
            summary = await generate_session_summary(
                client=self.client,
                config=session.config,
                previous_summary=existing.summary if existing is not None else "",
                messages=new_messages,
            )
            covered_until = history[-1].message_id or ""
            record = store.upsert_summary(
                session_id=session.session_id,
                covered_until_message_id=covered_until,
                summary=summary,
            )
            self._record(
                session,
                "conversation_summary_updated",
                {
                    "session_id": session.session_id,
                    "role_id": session.role_id,
                    "summary_id": record.summary_id,
                    "covered_until_message_id": record.covered_until_message_id,
                },
            )
        except Exception as summary_error:
            self._record(
                session,
                "conversation_summary_failed",
                {"session_id": session.session_id, "role_id": session.role_id, "message": str(summary_error)},
            )

    def _persist_session_participants(self, session_id: str, roles: list[RolePackage]) -> None:
        with self.database.connect() as connection:
            for index, role in enumerate(roles):
                connection.execute(
                    """
                    insert into session_participants (session_id, role_id, display_name, ordinal, status, visibility_json)
                    values (?, ?, ?, ?, ?, ?)
                    """,
                    (session_id, role.id, role.name, index, "active", "{}"),
                )

    def _visible_story_context(self, session_id: str, *, speaker_id: str | None = None) -> dict[str, Any]:
        try:
            return self.story_service.visible_context(session_id, speaker_id=speaker_id)
        except KeyError as error:
            raise SessionNotFoundError(session_id) from error

    def _persist_message(
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
        message = self.session_store.persist_message(
            session_id,
            role,
            content,
            speaker_id=speaker_id,
            input_modality=input_modality,
            output_modality=output_modality,
            emotion_label=emotion_label,
            audio_ref=audio_ref,
        )
        if session_id in self._sessions:
            stored = self.session_store.get_session(session_id)
            self._sessions[session_id].updated_at = stored.updated_at
            self._sessions[session_id].last_message_at = stored.last_message_at
        return message

    def _load_session(self, session_id: str) -> SessionState:
        try:
            stored = self.session_store.get_session(session_id)
        except KeyError as error:
            raise SessionNotFoundError(session_id) from error
        return self._state_from_stored_session(stored)

    def _state_from_stored_session(
        self,
        stored: StoredSession,
        *,
        role_opening: str | None = None,
        config: AppConfig | None = None,
        participants: list[dict[str, Any]] | None = None,
    ) -> SessionState:
        if role_opening is None:
            try:
                role_opening = self._resolve_role(stored.role_id).opening
            except Exception:
                role_opening = ""
        return SessionState(
            session_id=stored.session_id,
            role_id=stored.role_id,
            role_name=stored.role_name,
            role_version=stored.role_version,
            role_opening=role_opening,
            config=config or self.config,
            mode=stored.mode,
            scenario_id=stored.scenario_id,
            scenario_name=stored.scenario_name,
            participants=participants if participants is not None else self._load_participants(stored.session_id),
            title=stored.title,
            created_at=stored.created_at,
            updated_at=stored.updated_at,
            last_message_at=stored.last_message_at,
            status=stored.status,
            history=stored.history,
        )

    def _load_participants(self, session_id: str) -> list[dict[str, Any]]:
        rows = self.database.fetch_all(
            """
            select role_id, display_name, ordinal, status, visibility_json
            from session_participants
            where session_id = ?
            order by ordinal
            """,
            (session_id,),
        )
        return [
            {
                "roleId": str(row["role_id"]),
                "displayName": str(row["display_name"]),
                "ordinal": int(row["ordinal"]),
                "status": str(row["status"]),
                "visibility": json.loads(str(row["visibility_json"])),
            }
            for row in rows
        ]

    def _load_messages(self, session_id: str) -> list[ChatMessage]:
        return self.session_store.load_messages(session_id)

    def _session_summary_text(self, session_id: str) -> str | None:
        summary = SummaryStore(self.database).get_latest_summary(session_id)
        return summary.summary if summary is not None else None

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()


def _chat_message_response(message: ChatMessage) -> dict[str, str | None]:
    return {
        "messageId": message.message_id,
        "role": message.role,
        "content": message.content,
        "speakerId": message.speaker_id,
        "inputModality": message.input_modality,
        "outputModality": message.output_modality,
        "emotionLabel": message.emotion_label,
        "audioRef": message.audio_ref,
    }


def _relationship_response(relationship: RelationshipState | None) -> dict[str, object] | None:
    if relationship is None:
        return None
    return {
        "userId": relationship.user_id,
        "companionId": relationship.companion_id,
        "summary": relationship.summary,
        "familiarity": relationship.familiarity,
        "trust": relationship.trust,
        "preferredAddress": relationship.preferred_address,
        "communicationStyle": relationship.communication_style,
        "updatedAt": relationship.updated_at,
    }


def _memory_context_response(memory: MemoryRecord) -> dict[str, object]:
    return {
        "memoryId": memory.memory_id,
        "type": memory.type,
        "content": memory.content,
        "importance": memory.importance,
        "confidence": memory.confidence,
        "lastUsedAt": memory.last_used_at,
        "useCount": memory.use_count,
    }


__all__ = [
    "ChatMessage",
    "RuntimeEvent",
    "SessionManager",
    "SessionNotFoundError",
    "SessionState",
    "StreamEvent",
]
