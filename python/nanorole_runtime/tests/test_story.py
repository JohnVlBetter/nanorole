from pathlib import Path

from nanorole_runtime.scenarios import ScenarioPackage
from nanorole_runtime.storage import Database
from nanorole_runtime.story import StoryService


def scenario() -> ScenarioPackage:
    return ScenarioPackage(
        id="forgotten-observatory",
        name="Forgotten Observatory",
        version="1.0.0",
        description="A stalled observatory clock hides a missing archive.",
        mode="mystery",
        roles=["clockwork-sage"],
        world="A brass city where clocks regulate memory archives.",
        initial_scene="The observatory clock has stopped.",
        initial_state={"phase": "opening", "clock": "stopped"},
        public_facts=[{"id": "public-1", "content": "The public clock stopped at midnight."}],
        hidden_facts=[{"id": "hidden-1", "content": "The clock was stopped from inside.", "visibility": ["clockwork-sage"]}],
        clues=[{"id": "clue-1", "content": "A bent brass key rests under the dial.", "status": "hidden"}],
    )


def test_story_service_creates_state_and_returns_sanitized_context(tmp_path: Path) -> None:
    database = Database(tmp_path / "nanorole.sqlite3")
    database.initialize()
    service = StoryService(database)

    service.create_story_state("s1", scenario())

    state = service.get_state("s1")
    context = service.visible_context("s1")

    assert state["scenarioId"] == "forgotten-observatory"
    assert state["currentScene"] == "The observatory clock has stopped."
    assert state["initialState"]["phase"] == "opening"
    assert state["hiddenFacts"][0]["id"] == "hidden-1"
    assert context == {
        "currentScene": "The observatory clock has stopped.",
        "currentState": {"phase": "opening", "clock": "stopped"},
        "publicFacts": [{"id": "public-1", "content": "The public clock stopped at midnight."}],
        "revealedClues": [],
        "recentEvents": [],
    }


def test_story_service_appends_event_and_updates_state(tmp_path: Path) -> None:
    database = Database(tmp_path / "nanorole.sqlite3")
    database.initialize()
    service = StoryService(database)
    service.create_story_state("s1", scenario())

    event = service.append_event(
        "s1",
        "state_changed",
        {
            "currentScene": "The archive door is now open.",
            "statePatch": {"phase": "investigation"},
            "publicFact": {"id": "public-2", "content": "The archive door opened."},
        },
    )
    service.append_event("s1", "clue_revealed", {"clueId": "clue-1"})

    state = service.get_state("s1")
    context = service.visible_context("s1")

    assert event["type"] == "state_changed"
    assert event["ordinal"] == 0
    assert state["currentScene"] == "The archive door is now open."
    assert state["currentState"]["phase"] == "investigation"
    assert state["publicFacts"][1]["sourceEventId"] == event["eventId"]
    assert state["revealedClues"][0]["id"] == "clue-1"
    assert [item["type"] for item in context["recentEvents"]] == ["state_changed", "clue_revealed"]
    assert "hiddenFacts" not in context
