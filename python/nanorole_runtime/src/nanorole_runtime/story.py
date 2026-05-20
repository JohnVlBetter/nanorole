from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from .scenarios import ScenarioPackage
from .storage import Database


class StoryService:
    def __init__(self, database: Database) -> None:
        self.database = database

    def create_story_state(self, session_id: str, scenario: ScenarioPackage) -> None:
        now = _now()
        payload = {
            "initialState": scenario.initial_state,
            "currentState": scenario.initial_state,
            "publicFacts": scenario.public_facts,
            "hiddenFacts": scenario.hidden_facts,
            "clues": scenario.clues,
        }
        with self.database.connect() as connection:
            connection.execute(
                """
                insert into story_states (session_id, scenario_id, state_json, current_scene, created_at, updated_at)
                values (?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    scenario.id,
                    json.dumps(payload, ensure_ascii=False, sort_keys=True),
                    scenario.initial_scene,
                    now,
                    now,
                ),
            )

    def get_state(self, session_id: str) -> dict[str, Any]:
        row = self.database.fetch_one("select * from story_states where session_id = ?", (session_id,))
        if row is None:
            raise KeyError(session_id)
        state = json.loads(str(row["state_json"]))
        recent_events = self._load_scene_events(session_id)
        clues = list(state.get("clues", []))
        return {
            "sessionId": session_id,
            "scenarioId": str(row["scenario_id"]),
            "currentScene": str(row["current_scene"]),
            "initialState": state.get("initialState", {}),
            "currentState": state.get("currentState", state.get("initialState", {})),
            "publicFacts": state.get("publicFacts", []),
            "hiddenFacts": state.get("hiddenFacts", []),
            "clues": clues,
            "revealedClues": [clue for clue in clues if isinstance(clue, dict) and clue.get("status") == "revealed"],
            "recentEvents": recent_events,
        }

    def append_event(self, session_id: str, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not event_type.strip():
            raise ValueError("event type is required")
        if not isinstance(payload, dict):
            raise ValueError("event payload must be an object")
        story_row = self.database.fetch_one("select * from story_states where session_id = ?", (session_id,))
        if story_row is None:
            raise KeyError(session_id)

        now = _now()
        event_id = uuid.uuid4().hex
        clean_type = event_type.strip()
        with self.database.connect() as connection:
            row = connection.execute(
                "select coalesce(max(ordinal), -1) + 1 as ordinal from scene_events where session_id = ?",
                (session_id,),
            ).fetchone()
            ordinal = int(row["ordinal"])
            connection.execute(
                """
                insert into scene_events (id, session_id, type, payload_json, created_at, ordinal)
                values (?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    session_id,
                    clean_type,
                    json.dumps(payload, ensure_ascii=False, sort_keys=True),
                    now,
                    ordinal,
                ),
            )

        state = json.loads(str(story_row["state_json"]))
        current_scene = str(story_row["current_scene"])
        next_state, next_scene = self._apply_story_event_to_state(
            state=state,
            current_scene=current_scene,
            event_id=event_id,
            event_type=clean_type,
            payload=payload,
        )
        with self.database.connect() as connection:
            connection.execute(
                """
                update story_states
                set state_json = ?, current_scene = ?, updated_at = ?
                where session_id = ?
                """,
                (
                    json.dumps(next_state, ensure_ascii=False, sort_keys=True),
                    next_scene,
                    now,
                    session_id,
                ),
            )

        return {
            "eventId": event_id,
            "sessionId": session_id,
            "type": clean_type,
            "payload": payload,
            "createdAt": now,
            "ordinal": ordinal,
        }

    def visible_context(self, session_id: str, *, speaker_id: str | None = None) -> dict[str, Any]:
        state = self.get_state(session_id)
        context = {
            "currentScene": state["currentScene"],
            "currentState": state["currentState"],
            "publicFacts": state["publicFacts"],
            "revealedClues": state["revealedClues"],
            "recentEvents": state["recentEvents"],
        }
        if speaker_id:
            context["visibleHiddenFacts"] = [
                fact
                for fact in state.get("hiddenFacts", [])
                if isinstance(fact, dict)
                and isinstance(fact.get("visibility"), list)
                and speaker_id in fact["visibility"]
            ]
        return context

    def _apply_story_event_to_state(
        self,
        *,
        state: dict[str, Any],
        current_scene: str,
        event_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> tuple[dict[str, Any], str]:
        next_state = dict(state)
        next_scene = current_scene
        if isinstance(payload.get("currentScene"), str) and payload["currentScene"].strip():
            next_scene = payload["currentScene"].strip()

        current_state = dict(next_state.get("currentState") or next_state.get("initialState") or {})
        state_patch = payload.get("statePatch")
        if isinstance(state_patch, dict):
            current_state.update(state_patch)
        next_state["currentState"] = current_state

        public_fact = payload.get("publicFact")
        if isinstance(public_fact, dict):
            facts = [dict(item) for item in next_state.get("publicFacts", []) if isinstance(item, dict)]
            facts.append({**public_fact, "sourceEventId": event_id})
            next_state["publicFacts"] = facts

        if event_type == "clue_revealed":
            clue_id = payload.get("clueId")
            clues = []
            for item in next_state.get("clues", []):
                clue = dict(item) if isinstance(item, dict) else {"content": str(item)}
                if clue_id is not None and clue.get("id") == clue_id:
                    clue["status"] = "revealed"
                    clue["sourceEventId"] = event_id
                clues.append(clue)
            next_state["clues"] = clues

        return next_state, next_scene

    def _load_scene_events(self, session_id: str, *, limit: int = 20) -> list[dict[str, Any]]:
        rows = self.database.fetch_all(
            """
            select id, session_id, type, payload_json, created_at, ordinal
            from scene_events
            where session_id = ?
            order by ordinal desc
            limit ?
            """,
            (session_id, limit),
        )
        events = [
            {
                "eventId": str(row["id"]),
                "sessionId": str(row["session_id"]),
                "type": str(row["type"]),
                "payload": json.loads(str(row["payload_json"])),
                "createdAt": str(row["created_at"]),
                "ordinal": int(row["ordinal"]),
            }
            for row in rows
        ]
        return list(reversed(events))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
