from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, AsyncIterator, Callable

from .config import AppConfig
from .context import ContextAssembler
from .llm import ChatClient
from .memory import MemoryStore
from .roles import RolePackage
from .sessions_types import ChatMessage


@dataclass(frozen=True)
class TurnStreamEvent:
    type: str
    data: dict[str, Any]


PersistMessage = Callable[..., ChatMessage]
RecordEvent = Callable[[str, dict[str, Any]], None]
WriteLog = Callable[[str, dict[str, Any]], None]
ScheduleMemoryExtraction = Callable[..., None]
ScheduleSummaryUpdate = Callable[[], None]


class CompanionTurnPipeline:
    def __init__(
        self,
        *,
        session_id: str,
        role: RolePackage,
        config: AppConfig,
        client: ChatClient,
        history: list[ChatMessage],
        user_id: str,
        companion_id: str,
        session_summary: str | None,
        memory_store: MemoryStore,
        persist_message: PersistMessage,
        record_event: RecordEvent,
        write_log: WriteLog,
        schedule_memory_extraction: ScheduleMemoryExtraction,
        schedule_summary_update: ScheduleSummaryUpdate,
    ) -> None:
        self.session_id = session_id
        self.role = role
        self.config = config
        self.client = client
        self.history = history
        self.user_id = user_id
        self.companion_id = companion_id
        self.session_summary = session_summary
        self.memory_store = memory_store
        self.persist_message = persist_message
        self.record_event = record_event
        self.write_log = write_log
        self.schedule_memory_extraction = schedule_memory_extraction
        self.schedule_summary_update = schedule_summary_update

    async def stream(
        self,
        *,
        user_input: str,
        speaker_id: str | None,
        input_modality: str | None,
        emotion_label: str | None,
        audio_ref: str | None,
    ) -> AsyncIterator[TurnStreamEvent]:
        started = time.perf_counter()
        self.record_event(
            "turn_started",
            {
                "session_id": self.session_id,
                "role_id": self.role.id,
                "speaker_id": speaker_id or "user",
                "input_modality": input_modality or "text",
            },
        )
        user_message = self.persist_message(
            "user",
            user_input,
            speaker_id=speaker_id or "user",
            input_modality=input_modality or "text",
            emotion_label=emotion_label,
            audio_ref=audio_ref,
        )
        self.history.append(user_message)
        self.record_event(
            "user_message",
            {
                "session_id": self.session_id,
                "role_id": self.role.id,
                "message_id": user_message.message_id,
                "speaker_id": user_message.speaker_id,
                "input_modality": user_message.input_modality,
                "emotion_label": user_message.emotion_label,
                "audio_ref": user_message.audio_ref,
                "content": user_input,
            },
        )

        assistant_parts: list[str] = []
        messages: list[dict[str, str]] = []
        used_memory_ids: list[str] = []
        first_chunk_latency_ms: float | None = None
        first_token_latency_ms: float | None = None
        try:
            assembler = ContextAssembler(memory_store=self.memory_store)
            messages, used_memories = assembler.build_messages(
                role=self.role,
                user_id=self.user_id,
                companion_id=self.companion_id,
                history=self.history[:-1],
                user_input=user_input,
                session_summary=self.session_summary,
            )
            used_memory_ids = [memory.memory_id for memory in used_memories]
            self.memory_store.mark_used(used_memory_ids)
            self.record_event(
                "memory_retrieval",
                {"session_id": self.session_id, "role_id": self.role.id, "memory_ids": used_memory_ids},
            )
            self.record_event(
                "context_built",
                {
                    "session_id": self.session_id,
                    "role_id": self.role.id,
                    "message_count": len(messages),
                    "used_memory_ids": used_memory_ids,
                    "system_prompt_chars": len(messages[0]["content"]) if messages else 0,
                    "history_messages": max(len(messages) - 2, 0),
                    "has_session_summary": bool(self.session_summary and self.session_summary.strip()),
                },
            )
            if self.config.logging.trace_requests:
                self.write_log(
                    "trace_request",
                    {
                        "session_id": self.session_id,
                        "role_id": self.role.id,
                        "messages": messages,
                        "model": self.config.model.name,
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
                config=self.config,
                role=self.role,
                on_first_chunk=set_first_chunk_latency,
                on_first_token=set_first_token_latency,
            ):
                assistant_parts.append(chunk)
                self.record_event(
                    "assistant_delta",
                    {"session_id": self.session_id, "role_id": self.role.id, "delta": chunk},
                )
                yield TurnStreamEvent("token", {"delta": chunk})

            assistant_message = "".join(assistant_parts)
            assistant_chat_message = self.persist_message(
                "assistant",
                assistant_message,
                speaker_id=self.role.id,
                output_modality="text",
            )
            self.history.append(assistant_chat_message)
            self.record_event(
                "assistant_message",
                {
                    "session_id": self.session_id,
                    "role_id": self.role.id,
                    "message_id": assistant_chat_message.message_id,
                    "speaker_id": assistant_chat_message.speaker_id,
                    "output_modality": assistant_chat_message.output_modality,
                    "content": assistant_message,
                },
            )
            self.schedule_memory_extraction(
                user_message=user_message,
                user_text=user_input,
                assistant_message=assistant_chat_message,
                assistant_text=assistant_message,
            )
            self.schedule_summary_update()
            duration_ms = round((time.perf_counter() - started) * 1000, 3)
            self.write_log(
                "request_completed",
                {
                    "session_id": self.session_id,
                    "role_id": self.role.id,
                    "duration_ms": duration_ms,
                    "first_chunk_latency_ms": first_chunk_latency_ms,
                    "first_token_latency_ms": first_token_latency_ms,
                    "token_count": len(assistant_parts),
                    "input": {
                        "user_message": user_input,
                        "messages": messages,
                    },
                    "output": {
                        "message": assistant_message,
                        "chunks": assistant_parts,
                    },
                    "context": {
                        "used_memory_ids": used_memory_ids,
                        "message_count": len(messages),
                    },
                    "error": None,
                },
            )
            self.record_event(
                "turn_completed",
                {
                    "session_id": self.session_id,
                    "role_id": self.role.id,
                    "input_message_id": user_message.message_id,
                    "output_message_id": assistant_chat_message.message_id,
                    "duration_ms": duration_ms,
                    "token_count": len(assistant_parts),
                    "used_memory_ids": used_memory_ids,
                },
            )
            yield TurnStreamEvent("final", {"message": assistant_message})
        except Exception as error:
            self.record_event("error", {"session_id": self.session_id, "role_id": self.role.id, "message": str(error)})
            self.record_event("turn_failed", {"session_id": self.session_id, "role_id": self.role.id, "message": str(error)})
            self.write_log(
                "request_failed",
                {
                    "session_id": self.session_id,
                    "role_id": self.role.id,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 3),
                    "first_chunk_latency_ms": first_chunk_latency_ms,
                    "first_token_latency_ms": first_token_latency_ms,
                    "token_count": len(assistant_parts),
                    "input": {
                        "user_message": user_input,
                        "messages": messages,
                    },
                    "output": {
                        "message": "".join(assistant_parts),
                        "chunks": assistant_parts,
                    },
                    "context": {
                        "used_memory_ids": used_memory_ids,
                        "message_count": len(messages),
                    },
                    "error": str(error),
                },
            )
            yield TurnStreamEvent("error", {"message": str(error)})
