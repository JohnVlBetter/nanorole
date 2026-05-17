from pathlib import Path

from fastapi.testclient import TestClient

from nanorole_runtime.api import create_app
from nanorole_runtime.config import load_config
from nanorole_runtime.llm import ChatClient


class StubClient(ChatClient):
    async def stream_chat(self, *, messages, config, role, on_first_chunk=None, on_first_token=None):
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


def test_fastapi_routes_create_session_stream_and_export(tmp_path: Path) -> None:
    write_role(tmp_path)
    app = create_app(config=load_config(repo_root=tmp_path), client=StubClient())
    client = TestClient(app)

    health = client.get("/health")
    created = client.post("/v1/sessions", json={"role_id": "clockwork-sage"})
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
