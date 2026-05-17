from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .config import AppConfig
from .llm import ChatClient
from .sessions_types import ChatMessage
from .storage import Database


@dataclass(frozen=True)
class SummaryInput:
    previous_summary: str
    messages: list[ChatMessage]


@dataclass(frozen=True)
class SummaryRecord:
    summary_id: str
    session_id: str
    covered_until_message_id: str
    summary: str
    created_at: str
    updated_at: str


class SummaryStore:
    def __init__(self, database: Database) -> None:
        self.database = database

    def get_latest_summary(self, session_id: str) -> SummaryRecord | None:
        row = self.database.fetch_one(
            """
            select *
            from conversation_summaries
            where session_id = ?
            order by updated_at desc, created_at desc
            limit 1
            """,
            (session_id,),
        )
        if row is None:
            return None
        return self._row_to_summary(row)

    def get_covered_message_count(self, session_id: str) -> int:
        summary = self.get_latest_summary(session_id)
        if summary is None:
            return 0
        row = self.database.fetch_one(
            "select ordinal from messages where session_id = ? and id = ?",
            (session_id, summary.covered_until_message_id),
        )
        if row is None:
            return 0
        return int(row["ordinal"]) + 1

    def upsert_summary(self, *, session_id: str, covered_until_message_id: str, summary: str) -> SummaryRecord:
        clean_summary = summary.strip()
        if not clean_summary:
            raise ValueError("summary must be non-empty")
        if not covered_until_message_id.strip():
            raise ValueError("covered_until_message_id must be non-empty")
        existing = self.get_latest_summary(session_id)
        now = utc_now()
        with self.database.connect() as connection:
            if existing is None:
                summary_id = uuid.uuid4().hex
                connection.execute(
                    """
                    insert into conversation_summaries (
                      id, session_id, covered_until_message_id, summary, created_at, updated_at
                    ) values (?, ?, ?, ?, ?, ?)
                    """,
                    (summary_id, session_id, covered_until_message_id, clean_summary, now, now),
                )
            else:
                summary_id = existing.summary_id
                connection.execute(
                    """
                    update conversation_summaries
                    set covered_until_message_id = ?, summary = ?, updated_at = ?
                    where id = ?
                    """,
                    (covered_until_message_id, clean_summary, now, summary_id),
                )
        latest = self.get_latest_summary(session_id)
        if latest is None:
            raise KeyError(session_id)
        return latest

    def _row_to_summary(self, row: Any) -> SummaryRecord:
        return SummaryRecord(
            summary_id=str(row["id"]),
            session_id=str(row["session_id"]),
            covered_until_message_id=str(row["covered_until_message_id"]),
            summary=str(row["summary"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )


def should_update_summary(history: list[ChatMessage], existing_summary_message_count: int) -> bool:
    return len(history) - existing_summary_message_count >= 12


async def generate_session_summary(
    *,
    client: ChatClient,
    config: AppConfig,
    previous_summary: str,
    messages: list[ChatMessage],
) -> str:
    if not messages:
        return previous_summary.strip()
    try:
        raw = await client.complete_json(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Summarize the conversation for future context. "
                        "Return strict JSON with a single string key named summary. "
                        "Keep stable preferences, boundaries, decisions, and relationship progress. "
                        "Do not include transient moods unless they changed an ongoing plan."
                    ),
                },
                {
                    "role": "user",
                    "content": _summary_prompt(previous_summary=previous_summary, messages=messages),
                },
            ],
            config=config,
        )
        summary = raw.get("summary")
        if isinstance(summary, str) and summary.strip():
            return _trim_summary(summary)
    except Exception:
        pass
    return build_deterministic_summary(previous_summary=previous_summary, messages=messages)


def build_deterministic_summary(*, previous_summary: str, messages: list[ChatMessage]) -> str:
    lines = [f"{message.role}: {message.content.strip()}" for message in messages if message.content.strip()]
    recent = "\n".join(lines)
    if previous_summary.strip():
        text = f"{previous_summary.strip()}\n\nRecent conversation:\n{recent}"
    else:
        text = recent
    return _trim_summary(text)


def _summary_prompt(*, previous_summary: str, messages: list[ChatMessage]) -> str:
    previous = previous_summary.strip() or "No previous summary."
    transcript = "\n".join(f"{message.role}: {message.content.strip()}" for message in messages if message.content.strip())
    return f"Previous summary:\n{previous}\n\nNew messages:\n{transcript}"


def _trim_summary(summary: str, *, limit: int = 1800) -> str:
    normalized = "\n".join(line.strip() for line in summary.strip().splitlines() if line.strip())
    if len(normalized) <= limit:
        return normalized
    return normalized[-limit:].lstrip()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
