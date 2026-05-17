from __future__ import annotations

from dataclasses import dataclass

from .sessions_types import ChatMessage


@dataclass(frozen=True)
class SummaryInput:
    previous_summary: str
    messages: list[ChatMessage]


def should_update_summary(history: list[ChatMessage], existing_summary_message_count: int) -> bool:
    return len(history) - existing_summary_message_count >= 12
