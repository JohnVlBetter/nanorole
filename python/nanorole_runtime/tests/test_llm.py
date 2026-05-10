from pathlib import Path

from nanorole_runtime.config import load_config
from nanorole_runtime.llm import build_chat_payload
from nanorole_runtime.roles import RolePackage


def test_build_chat_payload_flattens_extra_body_for_openai_compatible_request(tmp_path: Path) -> None:
    config = load_config(
        repo_root=tmp_path,
        overrides={
            "model": {
                "provider": "deepseek",
                "name": "deepseek-v4-pro",
                "reasoning_effort": "high",
                "extra_body": {"thinking": {"type": "enabled"}},
            }
        },
    )
    role = RolePackage(
        id="clockwork-sage",
        name="Clockwork Sage",
        version="1.0.0",
        world="A city of brass towers.",
        background="The sage repairs memory machines.",
        persona="Measured, curious, precise.",
        goals=["Help the user uncover forgotten causes."],
        opening="The gears quiet as you enter.",
        style={"temperature": 0.8},
    )

    payload = build_chat_payload(
        config=config,
        role=role,
        messages=[{"role": "user", "content": "Hello"}],
    )

    assert payload == {
        "model": "deepseek-v4-pro",
        "messages": [{"role": "user", "content": "Hello"}],
        "stream": True,
        "temperature": 0.8,
        "reasoning_effort": "high",
        "thinking": {"type": "enabled"},
    }
