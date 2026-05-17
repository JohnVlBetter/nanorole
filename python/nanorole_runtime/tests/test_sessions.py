from pathlib import Path
import asyncio
import json

import pytest

from nanorole_runtime.config import load_config
from nanorole_runtime.llm import ChatClient
from nanorole_runtime.roles import RolePackage
from nanorole_runtime.sessions import SessionManager


class StubClient(ChatClient):
    def __init__(self, chunks: list[str]) -> None:
        self.chunks = chunks
        self.calls: list[list[dict[str, str]]] = []

    async def stream_chat(self, *, messages, config, role, on_first_chunk=None, on_first_token=None):
        self.calls.append(messages)
        if on_first_chunk is not None:
            on_first_chunk(12.34)
        if on_first_token is not None:
            on_first_token(56.78)
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


def create_role_file(path: Path, role: RolePackage) -> None:
    role_dir = path / "examples" / "roles" / role.id
    role_dir.mkdir(parents=True, exist_ok=True)
    (role_dir / "character.yaml").write_text(
        "\n".join(
            [
                f"id: {role.id!r}",
                f"name: {role.name!r}",
                f"version: {role.version!r}",
                f"world: {role.world!r}",
                f"background: {role.background!r}",
                f"persona: {role.persona!r}",
                "goals:",
                *[f"  - {item!r}" for item in role.goals],
                f"opening: {role.opening!r}",
            ]
        ),
        encoding="utf-8",
    )


async def test_sessions_keep_history_and_exports_isolated(tmp_path: Path, role: RolePackage) -> None:
    create_role_file(tmp_path, role)
    config = load_config(repo_root=tmp_path)
    client = StubClient(["hello", " world"])
    manager = SessionManager(config=config, client=client)

    first = manager.create_session(role.id)
    second = manager.create_session(role.id)
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
        async def stream_chat(self, *, messages, config, role, on_first_chunk=None, on_first_token=None):
            raise RuntimeError("model unavailable")
            yield ""

    create_role_file(tmp_path, role)
    manager = SessionManager(config=load_config(repo_root=tmp_path), client=BrokenClient())
    session = manager.create_session(role.id)

    events = [event async for event in manager.stream_message(session.session_id, "Hi")]

    assert events[0].type == "error"
    assert "model unavailable" in events[0].data["message"]
    assert '"type": "error"' in manager.export_session(session.session_id)


async def test_session_manager_writes_logs_trace_and_export_file(tmp_path: Path, role: RolePackage) -> None:
    create_role_file(tmp_path, role)
    config = load_config(
        repo_root=tmp_path,
        overrides={"logging": {"trace_requests": True}},
    )
    manager = SessionManager(config=config, client=StubClient(["hello"]))
    session = manager.create_session(role.id)

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


async def test_request_completed_log_includes_llm_input_and_output(tmp_path: Path, role: RolePackage) -> None:
    create_role_file(tmp_path, role)
    config = load_config(repo_root=tmp_path)
    client = StubClient(["hello", " world"])
    manager = SessionManager(config=config, client=client)
    session = manager.create_session(role.id)

    events = [event async for event in manager.stream_message(session.session_id, "Hi")]

    log_file = config.paths.logs_dir / "runtime.jsonl"
    logs = [json.loads(line) for line in log_file.read_text(encoding="utf-8").splitlines()]
    completed = next(entry for entry in logs if entry["type"] == "request_completed")

    assert events[-1].data["message"] == "hello world"
    assert completed["input"]["user_message"] == "Hi"
    assert completed["input"]["messages"] == client.calls[0]
    assert completed["output"]["message"] == "hello world"
    assert completed["output"]["chunks"] == ["hello", " world"]
    assert "first_token_latency_ms" in completed
    assert isinstance(completed["first_token_latency_ms"], (int, float))
    assert completed["first_token_latency_ms"] is not None
    assert "first_chunk_latency_ms" in completed
    assert isinstance(completed["first_chunk_latency_ms"], (int, float))
    assert completed["first_chunk_latency_ms"] is not None
    assert completed["first_token_latency_ms"] == 56.78
    assert completed["first_chunk_latency_ms"] == 12.34


async def test_slow_memory_extraction_does_not_block_final_stream_event(tmp_path: Path, role: RolePackage) -> None:
    class SlowExtractionClient(ChatClient):
        def __init__(self) -> None:
            self.release = asyncio.Event()

        async def stream_chat(self, *, messages, config, role, on_first_chunk=None, on_first_token=None):
            yield "hello"

        async def complete_json(self, *, messages, config):
            await self.release.wait()
            return {"memories": [], "archive_memory_ids": [], "relationship_patch": None}

    create_role_file(tmp_path, role)
    client = SlowExtractionClient()
    manager = SessionManager(config=load_config(repo_root=tmp_path), client=client)
    session = manager.create_session(role.id)
    stream = manager.stream_message(session.session_id, "Hi")

    token = await asyncio.wait_for(anext(stream), timeout=0.5)
    final = await asyncio.wait_for(anext(stream), timeout=0.5)
    client.release.set()

    assert token.type == "token"
    assert final.type == "final"
