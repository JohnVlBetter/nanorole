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


def create_scenario_file(path: Path) -> None:
    scenario_dir = path / "examples" / "scenarios" / "forgotten-observatory"
    scenario_dir.mkdir(parents=True, exist_ok=True)
    (scenario_dir / "scenario.yaml").write_text(
        "\n".join(
            [
                "id: forgotten-observatory",
                "name: Forgotten Observatory",
                "version: 1.0.0",
                "description: A stalled observatory clock hides a missing archive.",
                "mode: mystery",
                "roles:",
                "  - clockwork-sage",
                "  - neko-maid",
                "world: A brass city where public clocks regulate memory archives.",
                "initial_scene: The observatory clock has stopped...",
                "initial_state:",
                "  phase: opening",
                "  clock: stopped",
                "public_facts:",
                "  - id: public-1",
                "    content: The public clock stopped at midnight.",
                "hidden_facts:",
                "  - id: hidden-1",
                "    content: The clock was stopped from inside the archive room.",
                "    visibility:",
                "      - clockwork-sage",
                "clues:",
                "  - id: clue-1",
                "    content: A bent brass key rests under the dial.",
                "    status: hidden",
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


async def test_session_manager_creates_scenario_session_with_participants_and_initial_state(
    tmp_path: Path,
    role: RolePackage,
) -> None:
    create_role_file(tmp_path, role)
    create_role_file(
        tmp_path,
        RolePackage(
            id="neko-maid",
            name="Neko Maid",
            version="1.0.0",
            world="A brass city where public clocks regulate memory archives.",
            background="A quick observer who keeps the tea room ledger.",
            persona="Warm, direct, alert.",
            goals=["Notice small inconsistencies."],
            opening="Tea is ready.",
        ),
    )
    create_scenario_file(tmp_path)
    manager = SessionManager(config=load_config(repo_root=tmp_path), client=StubClient(["hello"]))

    session = manager.create_scenario_session("forgotten-observatory")
    loaded = manager.get_session(session.session_id)
    state = manager.get_story_state(session.session_id)

    assert loaded.mode == "scenario"
    assert loaded.scenario_id == "forgotten-observatory"
    assert loaded.scenario_name == "Forgotten Observatory"
    assert loaded.role_id == "clockwork-sage"
    assert [participant["roleId"] for participant in loaded.participants] == ["clockwork-sage", "neko-maid"]
    assert loaded.participants[0]["displayName"] == "Clockwork Sage"
    assert state["scenarioId"] == "forgotten-observatory"
    assert state["currentScene"] == "The observatory clock has stopped..."
    assert state["initialState"]["phase"] == "opening"


async def test_story_state_changes_when_story_event_is_appended(tmp_path: Path, role: RolePackage) -> None:
    create_role_file(tmp_path, role)
    create_role_file(
        tmp_path,
        RolePackage(
            id="neko-maid",
            name="Neko Maid",
            version="1.0.0",
            world="A brass city where public clocks regulate memory archives.",
            background="A quick observer who keeps the tea room ledger.",
            persona="Warm, direct, alert.",
            goals=["Notice small inconsistencies."],
            opening="Tea is ready.",
        ),
    )
    create_scenario_file(tmp_path)
    manager = SessionManager(config=load_config(repo_root=tmp_path), client=StubClient(["hello"]))
    session = manager.create_scenario_session("forgotten-observatory")

    event = manager.append_story_event(
        session.session_id,
        "state_changed",
        {
            "currentScene": "The archive door is now open.",
            "statePatch": {"phase": "investigation", "clock": "stopped"},
        },
    )
    state = manager.get_story_state(session.session_id)

    assert event["type"] == "state_changed"
    assert event["ordinal"] == 0
    assert state["currentScene"] == "The archive door is now open."
    assert state["currentState"]["phase"] == "investigation"
    assert state["recentEvents"][0]["eventId"] == event["eventId"]
    assert state["recentEvents"][0]["payload"]["statePatch"]["phase"] == "investigation"


async def test_clue_revealed_event_updates_story_state(tmp_path: Path, role: RolePackage) -> None:
    create_role_file(tmp_path, role)
    create_role_file(
        tmp_path,
        RolePackage(
            id="neko-maid",
            name="Neko Maid",
            version="1.0.0",
            world="A brass city where public clocks regulate memory archives.",
            background="A quick observer who keeps the tea room ledger.",
            persona="Warm, direct, alert.",
            goals=["Notice small inconsistencies."],
            opening="Tea is ready.",
        ),
    )
    create_scenario_file(tmp_path)
    manager = SessionManager(config=load_config(repo_root=tmp_path), client=StubClient(["hello"]))
    session = manager.create_scenario_session("forgotten-observatory")

    event = manager.append_story_event(session.session_id, "clue_revealed", {"clueId": "clue-1"})
    state = manager.get_story_state(session.session_id)

    assert state["clues"][0]["status"] == "revealed"
    assert state["clues"][0]["sourceEventId"] == event["eventId"]
    assert state["revealedClues"][0]["id"] == "clue-1"


async def test_context_preview_includes_visible_story_state_without_hidden_facts(
    tmp_path: Path,
    role: RolePackage,
) -> None:
    create_role_file(tmp_path, role)
    create_role_file(
        tmp_path,
        RolePackage(
            id="neko-maid",
            name="Neko Maid",
            version="1.0.0",
            world="A brass city where public clocks regulate memory archives.",
            background="A quick observer who keeps the tea room ledger.",
            persona="Warm, direct, alert.",
            goals=["Notice small inconsistencies."],
            opening="Tea is ready.",
        ),
    )
    create_scenario_file(tmp_path)
    manager = SessionManager(config=load_config(repo_root=tmp_path), client=StubClient(["hello"]))
    session = manager.create_scenario_session("forgotten-observatory")
    manager.append_story_event(session.session_id, "clue_revealed", {"clueId": "clue-1"})
    manager.append_story_event(
        session.session_id,
        "state_changed",
        {
            "currentScene": "The archive door is now open.",
            "statePatch": {"phase": "investigation"},
            "summary": "The archive door opened after the dial was inspected.",
        },
    )

    preview = manager.preview_context(session.session_id, user_input="What can I inspect?")
    system = preview["messages"][0]["content"]

    assert "Story state:" in system
    assert "The archive door is now open." in system
    assert "The public clock stopped at midnight." in system
    assert "A bent brass key rests under the dial." in system
    assert "The archive door opened after the dial was inspected." in system
    assert "The clock was stopped from inside the archive room." not in system
    assert preview["usedStory"]["publicFacts"][0]["id"] == "public-1"
    assert preview["usedStory"]["revealedClues"][0]["id"] == "clue-1"
    assert preview["usedStory"]["recentEvents"][-1]["type"] == "state_changed"


async def test_scenario_stream_message_uses_director_for_multiple_role_responses(
    tmp_path: Path,
    role: RolePackage,
) -> None:
    class MultiRoleClient(ChatClient):
        def __init__(self) -> None:
            self.director_calls = 0
            self.streamed_roles: list[str] = []
            self.user_message_counts_by_role: dict[str, int] = {}

        async def stream_chat(self, *, messages, config, role, on_first_chunk=None, on_first_token=None):
            self.streamed_roles.append(role.id)
            self.user_message_counts_by_role[role.id] = len([message for message in messages if message["role"] == "user"])
            yield f"{role.id} reply"

        async def complete_json(self, *, messages, config):
            if messages[0]["content"].startswith("You are the Nanorole scenario director."):
                self.director_calls += 1
                return {
                    "responses": [
                        {"speakerId": "clockwork-sage", "goal": "Explain what changed."},
                        {"speakerId": "neko-maid", "goal": "Point out the clue."},
                    ]
                }
            return {"memories": [], "archive_memory_ids": [], "relationship_patch": None}

    create_role_file(tmp_path, role)
    create_role_file(
        tmp_path,
        RolePackage(
            id="neko-maid",
            name="Neko Maid",
            version="1.0.0",
            world="A brass city where public clocks regulate memory archives.",
            background="A quick observer who keeps the tea room ledger.",
            persona="Warm, direct, alert.",
            goals=["Notice small inconsistencies."],
            opening="Tea is ready.",
        ),
    )
    create_scenario_file(tmp_path)
    client = MultiRoleClient()
    manager = SessionManager(config=load_config(repo_root=tmp_path), client=client)
    session = manager.create_scenario_session("forgotten-observatory")

    events = [event async for event in manager.stream_message(session.session_id, "What happens next?")]
    messages = manager.get_session(session.session_id).history
    assistant_messages = [message for message in messages if message.role == "assistant"]

    assert client.director_calls == 1
    assert client.streamed_roles == ["clockwork-sage", "neko-maid"]
    assert client.user_message_counts_by_role == {"clockwork-sage": 1, "neko-maid": 1}
    assert [message.speaker_id for message in assistant_messages] == ["clockwork-sage", "neko-maid"]
    assert [message.content for message in assistant_messages] == ["clockwork-sage reply", "neko-maid reply"]
    assert messages[0].role == "user"
    assert len([message for message in messages if message.role == "user"]) == 1
    assert [event.type for event in events] == ["director", "token", "final", "token", "final"]
    assert events[-1].data["messages"][1]["speakerId"] == "neko-maid"


async def test_scenario_director_falls_back_to_primary_role_for_invalid_selection(
    tmp_path: Path,
    role: RolePackage,
) -> None:
    class InvalidDirectorClient(ChatClient):
        def __init__(self) -> None:
            self.streamed_roles: list[str] = []

        async def stream_chat(self, *, messages, config, role, on_first_chunk=None, on_first_token=None):
            self.streamed_roles.append(role.id)
            yield "fallback reply"

        async def complete_json(self, *, messages, config):
            if messages[0]["content"].startswith("You are the Nanorole scenario director."):
                return {"responses": [{"speakerId": "unknown-role", "goal": "This should be ignored."}]}
            return {"memories": [], "archive_memory_ids": [], "relationship_patch": None}

    create_role_file(tmp_path, role)
    create_role_file(
        tmp_path,
        RolePackage(
            id="neko-maid",
            name="Neko Maid",
            version="1.0.0",
            world="A brass city where public clocks regulate memory archives.",
            background="A quick observer who keeps the tea room ledger.",
            persona="Warm, direct, alert.",
            goals=["Notice small inconsistencies."],
            opening="Tea is ready.",
        ),
    )
    create_scenario_file(tmp_path)
    client = InvalidDirectorClient()
    manager = SessionManager(config=load_config(repo_root=tmp_path), client=client)
    session = manager.create_scenario_session("forgotten-observatory")

    events = [event async for event in manager.stream_message(session.session_id, "Who answers?")]

    assert client.streamed_roles == ["clockwork-sage"]
    assert events[0].type == "director"
    assert events[0].data["fallback"] is True
    assert events[0].data["responses"][0]["speakerId"] == "clockwork-sage"
    assert events[-1].data["messages"][0]["speakerId"] == "clockwork-sage"


async def test_scenario_role_context_only_includes_hidden_facts_visible_to_speaker(
    tmp_path: Path,
    role: RolePackage,
) -> None:
    class InspectingClient(ChatClient):
        def __init__(self) -> None:
            self.system_prompts_by_role: dict[str, str] = {}

        async def stream_chat(self, *, messages, config, role, on_first_chunk=None, on_first_token=None):
            self.system_prompts_by_role[role.id] = messages[0]["content"]
            yield f"{role.id} saw context"

        async def complete_json(self, *, messages, config):
            if messages[0]["content"].startswith("You are the Nanorole scenario director."):
                return {
                    "responses": [
                        {"speakerId": "clockwork-sage", "goal": "Use only visible facts."},
                        {"speakerId": "neko-maid", "goal": "Use only visible facts."},
                    ]
                }
            return {"memories": [], "archive_memory_ids": [], "relationship_patch": None}

    create_role_file(tmp_path, role)
    create_role_file(
        tmp_path,
        RolePackage(
            id="neko-maid",
            name="Neko Maid",
            version="1.0.0",
            world="A brass city where public clocks regulate memory archives.",
            background="A quick observer who keeps the tea room ledger.",
            persona="Warm, direct, alert.",
            goals=["Notice small inconsistencies."],
            opening="Tea is ready.",
        ),
    )
    create_scenario_file(tmp_path)
    client = InspectingClient()
    manager = SessionManager(config=load_config(repo_root=tmp_path), client=client)
    session = manager.create_scenario_session("forgotten-observatory")

    _ = [event async for event in manager.stream_message(session.session_id, "What do you know?")]

    assert "The clock was stopped from inside the archive room." in client.system_prompts_by_role["clockwork-sage"]
    assert "The clock was stopped from inside the archive room." not in client.system_prompts_by_role["neko-maid"]


async def test_scenario_stream_message_records_context_and_memory_usage(
    tmp_path: Path,
    role: RolePackage,
) -> None:
    class InspectingClient(ChatClient):
        async def stream_chat(self, *, messages, config, role, on_first_chunk=None, on_first_token=None):
            yield "archive reply"

        async def complete_json(self, *, messages, config):
            if messages[0]["content"].startswith("You are the Nanorole scenario director."):
                return {"responses": [{"speakerId": "clockwork-sage", "goal": "Use relevant memory."}]}
            return {"memories": [], "archive_memory_ids": [], "relationship_patch": None}

    create_role_file(tmp_path, role)
    create_role_file(
        tmp_path,
        RolePackage(
            id="neko-maid",
            name="Neko Maid",
            version="1.0.0",
            world="A brass city where public clocks regulate memory archives.",
            background="A quick observer who keeps the tea room ledger.",
            persona="Warm, direct, alert.",
            goals=["Notice small inconsistencies."],
            opening="Tea is ready.",
        ),
    )
    create_scenario_file(tmp_path)
    manager = SessionManager(config=load_config(repo_root=tmp_path), client=InspectingClient())
    session = manager.create_scenario_session("forgotten-observatory")
    memory = MemoryStore(manager.database).create_memory(
        user_id="local-user",
        companion_id="clockwork-sage",
        memory_type="preference",
        content="The user wants archive clues explained plainly.",
        importance=0.8,
        confidence=0.9,
        source_message_ids=["seed"],
    )

    _ = [event async for event in manager.stream_message(session.session_id, "Explain the archive clue.")]
    refreshed = MemoryStore(manager.database).get_memory(memory.memory_id)
    exported = manager.export_session(session.session_id)

    assert refreshed.use_count == 1
    assert '"type": "memory_retrieval"' in exported
    assert '"type": "context_built"' in exported
    assert memory.memory_id in exported


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
    assert '"type": "turn_started"' in exported
    assert '"type": "user_message"' in exported
    assert '"type": "context_built"' in exported
    assert '"type": "assistant_delta"' in exported
    assert '"type": "assistant_message"' in exported
    assert '"type": "turn_completed"' in exported
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


async def test_chinese_do_not_remember_skips_memory_extraction(tmp_path: Path, role: RolePackage) -> None:
    class PrivacyClient(ChatClient):
        def __init__(self) -> None:
            self.extraction_calls = 0

        async def stream_chat(self, *, messages, config, role, on_first_chunk=None, on_first_token=None):
            yield "明白"

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

    _ = [event async for event in manager.stream_message(session.session_id, "不要记住这个：我喜欢可乐。")]
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
