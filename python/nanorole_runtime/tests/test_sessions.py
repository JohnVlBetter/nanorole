from pathlib import Path

import pytest

from nanorole_runtime.config import load_config
from nanorole_runtime.llm import ChatClient
from nanorole_runtime.roles import RolePackage
from nanorole_runtime.sessions import SessionManager


class StubClient(ChatClient):
    def __init__(self, chunks: list[str]) -> None:
        self.chunks = chunks
        self.calls: list[list[dict[str, str]]] = []

    async def stream_chat(self, *, messages, config, role):
        self.calls.append(messages)
        for chunk in self.chunks:
            yield chunk


@pytest.fixture
def role() -> RolePackage:
    return RolePackage(
        id="clockwork-sage",
        name="Clockwork Sage",
        version="1.0.0",
        world="A city of brass towers.",
        background="The sage repairs memory machines.",
        persona="Measured, curious, precise.",
        goals=["Help the user uncover forgotten causes."],
        opening="The gears quiet as you enter.",
    )


async def test_sessions_keep_history_and_exports_isolated(tmp_path: Path, role: RolePackage) -> None:
    config = load_config(repo_root=tmp_path)
    client = StubClient(["hello", " world"])
    manager = SessionManager(config=config, client=client)

    first = manager.create_session(role)
    second = manager.create_session(role)
    first_events = [event async for event in manager.stream_message(first.session_id, "Hi")]

    assert [event.type for event in first_events] == ["token", "token", "final"]
    assert first.history[-1].content == "hello world"
    assert second.history == []

    exported = manager.export_session(first.session_id)

    assert '"type": "session_started"' in exported
    assert '"type": "user_message"' in exported
    assert '"type": "assistant_delta"' in exported
    assert '"type": "assistant_message"' in exported
    assert second.session_id not in exported


async def test_stream_message_records_error_event(tmp_path: Path, role: RolePackage) -> None:
    class BrokenClient(ChatClient):
        async def stream_chat(self, *, messages, config, role):
            raise RuntimeError("model unavailable")
            yield ""

    manager = SessionManager(config=load_config(repo_root=tmp_path), client=BrokenClient())
    session = manager.create_session(role)

    events = [event async for event in manager.stream_message(session.session_id, "Hi")]

    assert events[0].type == "error"
    assert "model unavailable" in events[0].data["message"]
    assert '"type": "error"' in manager.export_session(session.session_id)


async def test_session_manager_writes_logs_trace_and_export_file(tmp_path: Path, role: RolePackage) -> None:
    config = load_config(
        repo_root=tmp_path,
        overrides={"logging": {"trace_requests": True}},
    )
    manager = SessionManager(config=config, client=StubClient(["hello"]))
    session = manager.create_session(role)

    events = [event async for event in manager.stream_message(session.session_id, "Hi")]
    exported = manager.export_session(session.session_id)

    log_file = config.paths.logs_dir / "runtime.jsonl"
    export_file = config.paths.sessions_dir / f"{session.session_id}.jsonl"
    log_text = log_file.read_text(encoding="utf-8")

    assert events[-1].data["message"] == "hello"
    assert export_file.read_text(encoding="utf-8") == exported
    assert '"type": "session_created"' in log_text
    assert '"type": "request_completed"' in log_text
    assert '"token_count": 1' in log_text
    assert '"type": "trace_request"' in log_text
    assert "OPENAI_API_KEY" not in log_text
