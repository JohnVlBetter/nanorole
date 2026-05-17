from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ChatMessage:
    role: str
    content: str
    message_id: str | None = None
    speaker_id: str | None = None
    input_modality: str | None = None
    output_modality: str | None = None
    emotion_label: str | None = None
    audio_ref: str | None = None
