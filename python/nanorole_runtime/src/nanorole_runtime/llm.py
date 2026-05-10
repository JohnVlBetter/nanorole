from __future__ import annotations

import json
from typing import Any, AsyncIterator, Protocol

import httpx

from .config import AppConfig
from .roles import RolePackage


class ChatClient(Protocol):
    async def stream_chat(
        self,
        *,
        messages: list[dict[str, str]],
        config: AppConfig,
        role: RolePackage,
    ) -> AsyncIterator[str]:
        ...


class OpenAICompatibleClient:
    async def stream_chat(
        self,
        *,
        messages: list[dict[str, str]],
        config: AppConfig,
        role: RolePackage,
    ) -> AsyncIterator[str]:
        if not config.model.api_key:
            raise RuntimeError("model API key is required for model requests")

        url = f"{config.model.base_url.rstrip('/')}/chat/completions"
        payload = build_chat_payload(config=config, role=role, messages=messages)

        headers = {
            "Authorization": f"Bearer {config.model.api_key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream("POST", url, json=payload, headers=headers) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = line.removeprefix("data: ").strip()
                    if data == "[DONE]":
                        break
                    chunk = json.loads(data)
                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                    content = delta.get("content")
                    if content:
                        yield content


def build_chat_payload(
    *,
    config: AppConfig,
    role: RolePackage,
    messages: list[dict[str, str]],
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": config.model.name,
        "messages": messages,
        "stream": True,
    }
    if "temperature" in role.style:
        payload["temperature"] = role.style["temperature"]
    if config.model.reasoning_effort:
        payload["reasoning_effort"] = config.model.reasoning_effort
    payload.update(config.model.extra_body)
    return payload
