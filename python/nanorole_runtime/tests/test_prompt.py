from nanorole_runtime.prompt import build_messages
from nanorole_runtime.roles import RolePackage
from nanorole_runtime.sessions import ChatMessage


def test_build_messages_includes_role_fields_history_and_current_user_input() -> None:
    role = RolePackage(
        id="clockwork-sage",
        name="Clockwork Sage",
        version="1.0.0",
        world="A city of brass towers.",
        background="The sage repairs memory machines.",
        persona="Measured, curious, precise.",
        goals=["Help the user uncover forgotten causes."],
        opening="The gears quiet as you enter.",
        safety_rules=["Never leave character."],
    )
    history = [
        ChatMessage(role="user", content="Where am I?"),
        ChatMessage(role="assistant", content="In the lower gearworks."),
    ]

    messages = build_messages(role, history, "What should I inspect?")

    assert messages[0]["role"] == "system"
    assert "A city of brass towers." in messages[0]["content"]
    assert "Never leave character." in messages[0]["content"]
    assert messages[1:] == [
        {"role": "user", "content": "Where am I?"},
        {"role": "assistant", "content": "In the lower gearworks."},
        {"role": "user", "content": "What should I inspect?"},
    ]

