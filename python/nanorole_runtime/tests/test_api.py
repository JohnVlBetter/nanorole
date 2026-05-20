from pathlib import Path

from fastapi.testclient import TestClient

from nanorole_runtime.api import create_app
from nanorole_runtime.config import load_config
from nanorole_runtime.llm import ChatClient


class StubClient(ChatClient):
    async def stream_chat(self, *, messages, config, role, on_first_chunk=None, on_first_token=None):
        yield "first"
        yield " second"

    async def complete_json(self, *, messages, config):
        return {"memories": [], "archive_memory_ids": [], "relationship_patch": None}


def role_payload() -> dict[str, object]:
    return {
        "id": "clockwork-sage",
        "name": "Clockwork Sage",
        "version": "1.0.0",
        "world": "A city of brass towers.",
        "background": "The sage repairs memory machines.",
        "persona": "Measured, curious, precise.",
        "goals": ["Help the user uncover forgotten causes."],
        "opening": "The gears quiet as you enter.",
    }


def write_role(tmp_path: Path) -> None:
    role_dir = tmp_path / "examples" / "roles" / "clockwork-sage"
    role_dir.mkdir(parents=True, exist_ok=True)
    lines = []
    for key, value in role_payload().items():
        if isinstance(value, list):
            lines.append(f"{key}:")
            lines.extend(f"  - {item}" for item in value)
        elif isinstance(value, dict):
            lines.append(f"{key}:")
            lines.extend(f"  {item_key}: {item_value}" for item_key, item_value in value.items())
        else:
            lines.append(f"{key}: {value!r}")
    (role_dir / "character.yaml").write_text("\n".join(lines), encoding="utf-8")


def write_neko_role(tmp_path: Path) -> None:
    role_dir = tmp_path / "examples" / "roles" / "neko-maid"
    role_dir.mkdir(parents=True, exist_ok=True)
    (role_dir / "character.yaml").write_text(
        "\n".join(
            [
                "id: neko-maid",
                "name: Neko Maid",
                "version: 1.0.0",
                "world: A city of brass towers.",
                "background: Keeps the tea room ledger.",
                "persona: Warm, direct, alert.",
                "goals:",
                "  - Notice small inconsistencies.",
                "opening: Tea is ready.",
            ]
        ),
        encoding="utf-8",
    )


def write_scenario(tmp_path: Path) -> None:
    scenario_dir = tmp_path / "examples" / "scenarios" / "forgotten-observatory"
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


def test_fastapi_routes_create_session_stream_and_export(tmp_path: Path) -> None:
    write_role(tmp_path)
    app = create_app(config=load_config(repo_root=tmp_path), client=StubClient())
    client = TestClient(app)

    health = client.get("/health")
    created = client.post("/v1/sessions", json={"role_id": "clockwork-sage"})
    session_id = created.json()["sessionId"]
    streamed = client.post(
        f"/v1/sessions/{session_id}/messages:stream",
        json={"message": "Hello", "inputModality": "text", "emotionLabel": "curious", "audioRef": "mic://sample"},
    )
    preview = client.get(f"/v1/sessions/{session_id}/context-preview?userInput=Next")
    messages = client.get(f"/v1/sessions/{session_id}/messages")
    exported = client.get(f"/v1/sessions/{session_id}/export")

    assert health.json() == {"status": "ok", "service": "nanorole-runtime"}
    assert created.status_code == 200
    assert created.json()["mode"] == "companion"
    assert created.json()["opening"] == "The gears quiet as you enter."
    assert streamed.status_code == 200
    assert "event: token" in streamed.text
    assert '"delta": "first"' in streamed.text
    assert "event: final" in streamed.text
    assert '"message": "first second"' in streamed.text
    assert preview.status_code == 200
    assert preview.json()["sessionId"] == session_id
    assert preview.json()["mode"] == "companion"
    assert preview.json()["systemPrompt"]
    assert preview.json()["context"]["world"] == "A city of brass towers."
    assert "selectedMemories" in preview.json()["context"]
    assert "sessionSummary" in preview.json()["context"]
    assert "story" in preview.json()["context"]
    assert preview.json()["messages"][-1] == {"role": "user", "content": "Next"}
    assert messages.json()["messages"][0] == {
        "messageId": messages.json()["messages"][0]["messageId"],
        "role": "user",
        "content": "Hello",
        "speakerId": "user",
        "inputModality": "text",
        "outputModality": None,
        "emotionLabel": "curious",
        "audioRef": "mic://sample",
    }
    assert messages.json()["messages"][1]["speakerId"] == "clockwork-sage"
    assert messages.json()["messages"][1]["inputModality"] is None
    assert messages.json()["messages"][1]["outputModality"] == "text"
    assert exported.status_code == 200
    assert '"type": "assistant_message"' in exported.text


def test_fastapi_scenario_routes_and_create_session(tmp_path: Path) -> None:
    write_role(tmp_path)
    write_neko_role(tmp_path)
    write_scenario(tmp_path)
    app = create_app(config=load_config(repo_root=tmp_path), client=StubClient())
    client = TestClient(app)

    listed = client.get("/v1/scenarios")
    detail = client.get("/v1/scenarios/forgotten-observatory")
    created = client.post("/v1/sessions", json={"mode": "scenario", "scenarioId": "forgotten-observatory"})
    session_id = created.json()["sessionId"] if created.status_code == 200 else "missing"
    fetched = client.get(f"/v1/sessions/{session_id}")
    story_state = client.get(f"/v1/sessions/{session_id}/story-state")

    assert listed.status_code == 200
    assert listed.json()["scenarios"][0]["scenarioId"] == "forgotten-observatory"
    assert listed.json()["scenarios"][0]["roleIds"] == ["clockwork-sage", "neko-maid"]
    assert detail.status_code == 200
    assert detail.json()["initialScene"] == "The observatory clock has stopped..."
    assert detail.json()["initialState"]["phase"] == "opening"
    assert created.status_code == 200
    assert created.json()["mode"] == "scenario"
    assert created.json()["scenarioId"] == "forgotten-observatory"
    assert created.json()["participants"][0]["roleId"] == "clockwork-sage"
    assert fetched.status_code == 200
    assert fetched.json()["participants"][1]["roleId"] == "neko-maid"
    assert story_state.status_code == 200
    assert story_state.json()["initialState"]["phase"] == "opening"


def test_fastapi_accepts_single_role_camel_case_create_request(tmp_path: Path) -> None:
    write_role(tmp_path)
    app = create_app(config=load_config(repo_root=tmp_path), client=StubClient())
    client = TestClient(app)

    created = client.post("/v1/sessions", json={"mode": "companion", "roleId": "clockwork-sage"})

    assert created.status_code == 200
    assert created.json()["mode"] == "companion"
    assert created.json()["roleId"] == "clockwork-sage"


def test_fastapi_accepts_single_role_story_alias_without_multi_role_participants(tmp_path: Path) -> None:
    write_role(tmp_path)
    write_neko_role(tmp_path)
    write_scenario(tmp_path)
    app = create_app(config=load_config(repo_root=tmp_path), client=StubClient())
    client = TestClient(app)

    created = client.post(
        "/v1/sessions",
        json={"mode": "story", "roleId": "clockwork-sage", "scenarioId": "forgotten-observatory"},
    )

    assert created.status_code == 200
    assert created.json()["mode"] == "story"
    assert created.json()["roleId"] == "clockwork-sage"
    assert len(created.json()["participants"]) <= 1


def test_fastapi_appends_story_events_and_updates_story_state(tmp_path: Path) -> None:
    write_role(tmp_path)
    write_neko_role(tmp_path)
    write_scenario(tmp_path)
    app = create_app(config=load_config(repo_root=tmp_path), client=StubClient())
    client = TestClient(app)
    session_id = client.post("/v1/sessions", json={"mode": "scenario", "scenarioId": "forgotten-observatory"}).json()["sessionId"]

    appended = client.post(
        f"/v1/sessions/{session_id}/events",
        json={
            "type": "state_changed",
            "payload": {
                "currentScene": "The archive door is now open.",
                "statePatch": {"phase": "investigation"},
            },
        },
    )
    story_state = client.get(f"/v1/sessions/{session_id}/story-state")

    assert appended.status_code == 200
    assert appended.json()["eventId"]
    assert appended.json()["type"] == "state_changed"
    assert appended.json()["ordinal"] == 0
    assert story_state.json()["currentScene"] == "The archive door is now open."
    assert story_state.json()["currentState"]["phase"] == "investigation"
    assert story_state.json()["recentEvents"][0]["eventId"] == appended.json()["eventId"]


def test_fastapi_route_updates_session_title_and_status(tmp_path: Path) -> None:
    write_role(tmp_path)
    app = create_app(config=load_config(repo_root=tmp_path), client=StubClient())
    client = TestClient(app)
    session_id = client.post("/v1/sessions", json={"role_id": "clockwork-sage"}).json()["sessionId"]

    updated = client.patch(
        f"/v1/sessions/{session_id}",
        json={"title": "Evening check-in", "status": "archived"},
    )
    fetched = client.get(f"/v1/sessions/{session_id}")

    assert updated.status_code == 200
    assert updated.json()["title"] == "Evening check-in"
    assert updated.json()["status"] == "archived"
    assert fetched.json()["title"] == "Evening check-in"
    assert fetched.json()["status"] == "archived"


def test_fastapi_route_rejects_invalid_session_status(tmp_path: Path) -> None:
    write_role(tmp_path)
    app = create_app(config=load_config(repo_root=tmp_path), client=StubClient())
    client = TestClient(app)
    session_id = client.post("/v1/sessions", json={"role_id": "clockwork-sage"}).json()["sessionId"]

    response = client.patch(f"/v1/sessions/{session_id}", json={"status": "hidden"})

    assert response.status_code == 400
    assert "invalid session status" in response.text


def test_fastapi_route_soft_deletes_session(tmp_path: Path) -> None:
    write_role(tmp_path)
    app = create_app(config=load_config(repo_root=tmp_path), client=StubClient())
    client = TestClient(app)
    session_id = client.post("/v1/sessions", json={"role_id": "clockwork-sage"}).json()["sessionId"]

    deleted = client.patch(f"/v1/sessions/{session_id}", json={"status": "deleted"})
    fetched = client.get(f"/v1/sessions/{session_id}")
    listed = client.get("/v1/sessions")

    assert deleted.status_code == 200
    assert deleted.json()["status"] == "deleted"
    assert fetched.status_code == 404
    assert all(item["sessionId"] != session_id for item in listed.json()["sessions"])


def test_memory_responses_include_source_message_content(tmp_path: Path) -> None:
    write_role(tmp_path)
    app = create_app(config=load_config(repo_root=tmp_path), client=StubClient())
    client = TestClient(app)
    session_id = client.post("/v1/sessions", json={"role_id": "clockwork-sage"}).json()["sessionId"]
    client.post(f"/v1/sessions/{session_id}/messages:stream", json={"message": "Remember that I like tea."})
    messages = client.get(f"/v1/sessions/{session_id}/messages").json()["messages"]
    user_message_id = messages[0]["messageId"]

    created = client.post(
        "/v1/memories",
        json={
            "companionId": "clockwork-sage",
            "type": "preference",
            "content": "The user likes tea.",
            "importance": 0.7,
            "confidence": 0.9,
            "sourceMessageIds": [user_message_id],
        },
    )
    listed = client.get("/v1/memories?userId=local-user&companionId=clockwork-sage")

    assert created.status_code == 200
    assert listed.json()["memories"][0]["sourceMessages"] == [
        {"messageId": user_message_id, "role": "user", "content": "Remember that I like tea."}
    ]


def test_create_session_requires_existing_role(tmp_path: Path) -> None:
    app = create_app(config=load_config(repo_root=tmp_path), client=StubClient())
    client = TestClient(app)

    response = client.post("/v1/sessions", json={"role_id": "missing-role"})

    assert response.status_code == 404
    assert "role not found" in response.text


def test_python_runtime_does_not_serve_demo_or_log_viewer(tmp_path: Path) -> None:
    client = TestClient(create_app(config=load_config(repo_root=tmp_path), client=StubClient()))

    assert client.get("/chat").status_code == 404
    assert client.get("/logs").status_code == 404
    assert client.get("/v1/logs").status_code == 404
    assert client.get("/v1/roles").status_code == 404
