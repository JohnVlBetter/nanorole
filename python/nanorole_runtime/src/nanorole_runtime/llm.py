from __future__ import annotations

import json
import time
from typing import Any, AsyncIterator, Callable, Protocol

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
        on_first_chunk: Callable[[float], None] | None = ...,
        on_first_token: Callable[[float], None] | None = ...,
    ) -> AsyncIterator[str]:
        ...


class OpenAICompatibleClient:
    async def stream_chat(
        self,
        *,
        messages: list[dict[str, str]],
        config: AppConfig,
        role: RolePackage,
        on_first_chunk: Callable[[float], None] | None = None,
        on_first_token: Callable[[float], None] | None = None,
    ) -> AsyncIterator[str]:
        started = time.perf_counter()
        first_chunk_reported = False
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
                    if not first_chunk_reported:
                        first_chunk_reported = True
                        if on_first_chunk is not None:
                            on_first_chunk((time.perf_counter() - started) * 1000)
                    data = line.removeprefix("data: ").strip()
                    if data == "[DONE]":
                        break
                    chunk = json.loads(data)
                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                    content = delta.get("content")
                    if content:
                        if on_first_token is not None:
                            on_first_token((time.perf_counter() - started) * 1000)
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
