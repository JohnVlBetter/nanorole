from pathlib import Path
import asyncio
import json

import pytest

from nanorole_runtime.config import load_config
from nanorole_runtime.llm import ChatClient
from nanorole_runtime.memory import MemoryStore
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

    async def complete_json(self, *, messages, config):
        return {"memories": [], "archive_memory_ids": [], "relationship_patch": None}


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


async def wait_until(predicate, *, timeout: float = 1.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("condition was not met before timeout")


async def test_update_session_mutates_title_and_status(tmp_path: Path, role: RolePackage) -> None:
    create_role_file(tmp_path, role)
    manager = SessionManager(config=load_config(repo_root=tmp_path), client=StubClient(["hello"]))
    session = manager.create_session(role.id)

    updated = manager.update_session(session.session_id, title="Evening check-in", status="archived")

    assert updated.title == "Evening check-in"
    assert updated.status == "archived"
    assert manager.get_session(session.session_id).title == "Evening check-in"


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


async def test_stream_message_background_extraction_writes_durable_memory(tmp_path: Path, role: RolePackage) -> None:
    class ExtractingClient(ChatClient):
        async def stream_chat(self, *, messages, config, role, on_first_chunk=None, on_first_token=None):
            yield "noted"

        async def complete_json(self, *, messages, config):
            prompt = messages[-1]["content"]
            user_message_id = next(line.split(": ", 1)[1] for line in prompt.splitlines() if line.startswith("user_message_id: "))
            return {
                "memories": [
                    {
                        "type": "preference",
                        "content": "The user prefers calm check-ins.",
                        "importance": 0.8,
                        "confidence": 0.9,
                        "source_message_ids": [user_message_id],
                    }
                ],
                "archive_memory_ids": [],
                "relationship_patch": None,
            }

    create_role_file(tmp_path, role)
    manager = SessionManager(config=load_config(repo_root=tmp_path), client=ExtractingClient())
    session = manager.create_session(role.id)

    events = [event async for event in manager.stream_message(session.session_id, "Please remember that I prefer calm check-ins.")]
    store = MemoryStore(manager.database)
    await wait_until(lambda: len(store.list_memories(user_id="local-user", companion_id=role.id)) == 1)

    memories = store.list_memories(user_id="local-user", companion_id=role.id)
    assert events[-1].type == "final"
    assert memories[0].content == "The user prefers calm check-ins."
    assert len(memories[0].source_message_ids) == 1


async def test_do_not_remember_this_skips_memory_extraction(tmp_path: Path, role: RolePackage) -> None:
    class PrivacyClient(ChatClient):
        def __init__(self) -> None:
            self.extraction_calls = 0

        async def stream_chat(self, *, messages, config, role, on_first_chunk=None, on_first_token=None):
            yield "understood"

        async def complete_json(self, *, messages, config):
            self.extraction_calls += 1
            return {
                "memories": [
                    {
                        "type": "preference",
                        "content": "The user likes cola.",
                        "importance": 0.8,
                        "confidence": 0.9,
                        "source_message_ids": ["m1"],
                    }
                ],
                "archive_memory_ids": [],
                "relationship_patch": None,
            }

    create_role_file(tmp_path, role)
    client = PrivacyClient()
    manager = SessionManager(config=load_config(repo_root=tmp_path), client=client)
    session = manager.create_session(role.id)

    _ = [event async for event in manager.stream_message(session.session_id, "Do not remember this: I like cola.")]
    await asyncio.sleep(0.05)

    store = MemoryStore(manager.database)
    assert client.extraction_calls == 0
    assert store.list_memories(user_id="local-user", companion_id=role.id) == []


async def test_stream_message_updates_conversation_summary(tmp_path: Path, role: RolePackage) -> None:
    class SummaryClient(ChatClient):
        async def stream_chat(self, *, messages, config, role, on_first_chunk=None, on_first_token=None):
            yield "reply"

        async def complete_json(self, *, messages, config):
            if "Summarize the conversation" in messages[0]["content"]:
                return {"summary": "The user is checking in regularly and prefers calm pacing."}
            return {"memories": [], "archive_memory_ids": [], "relationship_patch": None}

    create_role_file(tmp_path, role)
    manager = SessionManager(config=load_config(repo_root=tmp_path), client=SummaryClient())
    session = manager.create_session(role.id)

    for index in range(6):
        _ = [event async for event in manager.stream_message(session.session_id, f"Turn {index}")]

    await wait_until(
        lambda: manager.database.fetch_one("select summary from conversation_summaries where session_id = ?", (session.session_id,))
        is not None
    )
    preview = manager.preview_context(session.session_id, user_input="Continue?")
    system = preview["messages"][0]["content"]

    assert "Current session summary:" in system
    assert "The user is checking in regularly and prefers calm pacing." in system
