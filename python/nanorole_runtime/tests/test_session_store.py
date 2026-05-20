from pathlib import Path

from nanorole_runtime.session_store import SessionStore
from nanorole_runtime.sessions_types import ChatMessage
from nanorole_runtime.storage import Database


def test_session_store_creates_loads_and_updates_single_role_session(tmp_path: Path) -> None:
    database = Database(tmp_path / "nanorole.sqlite3")
    database.initialize()
    store = SessionStore(database)

    created = store.create_session(
        user_id="local-user",
        companion_id="clockwork-sage",
        role_id="clockwork-sage",
        role_name="Clockwork Sage",
        role_version="1.0.0",
        mode="companion",
        scenario_id=None,
        scenario_name=None,
    )
    loaded = store.get_session(created.session_id)

    assert loaded.session_id == created.session_id
    assert loaded.role_id == "clockwork-sage"
    assert loaded.mode == "companion"
    assert loaded.history == []

    updated = store.update_session(created.session_id, title="Evening check-in", status="archived")

    assert updated.title == "Evening check-in"
    assert updated.status == "archived"


def test_session_store_persists_messages_and_events_in_order(tmp_path: Path) -> None:
    database = Database(tmp_path / "nanorole.sqlite3")
    database.initialize()
    store = SessionStore(database)
    session = store.create_session(
        user_id="local-user",
        companion_id="clockwork-sage",
        role_id="clockwork-sage",
        role_name="Clockwork Sage",
        role_version="1.0.0",
        mode="companion",
        scenario_id=None,
        scenario_name=None,
    )

    user_message = store.persist_message(
        session.session_id,
        "user",
        "Hello",
        speaker_id="user",
        input_modality="text",
    )
    assistant_message = store.persist_message(
        session.session_id,
        "assistant",
        "The gears quiet.",
        speaker_id="clockwork-sage",
        output_modality="text",
    )
    store.record_event(session.session_id, "context_built", {"message_count": 2})

    loaded_messages = store.load_messages(session.session_id)
    events = store.load_events(session.session_id)

    assert loaded_messages == [
        ChatMessage(
            message_id=user_message.message_id,
            role="user",
            content="Hello",
            speaker_id="user",
            input_modality="text",
        ),
        ChatMessage(
            message_id=assistant_message.message_id,
            role="assistant",
            content="The gears quiet.",
            speaker_id="clockwork-sage",
            output_modality="text",
        ),
    ]
    assert events[0]["type"] == "context_built"
    assert events[0]["payload"]["message_count"] == 2
