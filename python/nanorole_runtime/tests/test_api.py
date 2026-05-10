from pathlib import Path

from fastapi.testclient import TestClient

from nanorole_runtime.api import create_app
from nanorole_runtime.config import load_config
from nanorole_runtime.llm import ChatClient
from nanorole_runtime.roles import RolePackage


class StubClient(ChatClient):
    async def stream_chat(self, *, messages, config, role):
        yield "first"
        yield " second"


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


def test_fastapi_routes_create_session_stream_and_export(tmp_path: Path) -> None:
    app = create_app(config=load_config(repo_root=tmp_path), client=StubClient())
    client = TestClient(app)

    health = client.get("/health")
    created = client.post("/v1/sessions", json={"role": role_payload()})
    session_id = created.json()["sessionId"]
    streamed = client.post(
        f"/v1/sessions/{session_id}/messages:stream",
        json={"message": "Hello"},
    )
    exported = client.get(f"/v1/sessions/{session_id}/export")

    assert health.json() == {"status": "ok", "service": "nanorole-runtime"}
    assert created.status_code == 200
    assert created.json()["opening"] == "The gears quiet as you enter."
    assert streamed.status_code == 200
    assert "event: token" in streamed.text
    assert '"delta": "first"' in streamed.text
    assert "event: final" in streamed.text
    assert '"message": "first second"' in streamed.text
    assert exported.status_code == 200
    assert '"type": "assistant_message"' in exported.text

