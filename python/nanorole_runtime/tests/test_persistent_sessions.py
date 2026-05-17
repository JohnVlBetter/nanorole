from __future__ import annotations

from pathlib import Path
from typing import AsyncIterator, Callable

import pytest

from nanorole_runtime.config import load_config
from nanorole_runtime.llm import ChatClient
from nanorole_runtime.roles import RolePackage
from nanorole_runtime.sessions import SessionManager


class FakeClient(ChatClient):
    async def stream_chat(
        self,
        *,
        messages: list[dict[str, str]],
        config,
        role: RolePackage,
        on_first_chunk: Callable[[float], None] | None = None,
        on_first_token: Callable[[float], None] | None = None,
    ) -> AsyncIterator[str]:
        yield "hello"


def write_role(root: Path) -> None:
    role_dir = root / "examples" / "roles" / "companion"
    role_dir.mkdir(parents=True)
    (role_dir / "character.yaml").write_text(
        """
id: companion
name: Companion
version: 1.0.0
world: A quiet local test world.
background: A kind companion for persistence tests.
persona: Gentle and concise.
goals:
  - Help the user feel heard.
opening: Hello.
""".strip(),
        encoding="utf-8",
    )


@pytest.mark.asyncio
async def test_session_and_messages_persist_across_managers(tmp_path: Path) -> None:
    write_role(tmp_path)
    config = load_config(repo_root=tmp_path)
    manager = SessionManager(config=config, client=FakeClient())
    session = manager.create_session("companion")

    events = []
    async for event in manager.stream_message(session.session_id, "I had a long day."):
        events.append(event)

    restored = SessionManager(config=config, client=FakeClient())
    loaded = restored.get_session(session.session_id)

    assert loaded.session_id == session.session_id
    assert [message.role for message in loaded.history] == ["user", "assistant"]
    assert loaded.history[0].content == "I had a long day."
    assert loaded.history[1].content == "hello"


def test_list_sessions_returns_persisted_session(tmp_path: Path) -> None:
    write_role(tmp_path)
    config = load_config(repo_root=tmp_path)
    manager = SessionManager(config=config, client=FakeClient())
    session = manager.create_session("companion")

    listed = manager.list_sessions()

    assert [item.session_id for item in listed] == [session.session_id]
