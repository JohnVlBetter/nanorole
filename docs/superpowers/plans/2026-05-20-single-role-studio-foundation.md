# Single-Role Studio Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor Nanorole around a single-role companion runtime with explicit context packages, clear persistence boundaries, and an optional single-role story layer while preserving current API behavior.

**Architecture:** Keep `SessionManager` as the public runtime facade, but move persistence and optional story operations into focused services. `ContextAssembler` will return a structured `ContextPackage` so workbench and logs can explain world, relationship, memory, summary, and story inputs without parsing prompt text.

**Tech Stack:** Python 3.12, FastAPI, SQLite, pytest, TypeScript, Vitest, Yarn workspaces.

---

## File Structure

- Create: `python/nanorole_runtime/src/nanorole_runtime/session_store.py`
  Owns session/message/event database reads and writes.
- Create: `python/nanorole_runtime/src/nanorole_runtime/story.py`
  Owns optional single-role story state and sanitized story context.
- Modify: `python/nanorole_runtime/src/nanorole_runtime/context.py`
  Adds `ContextPackage` and keeps legacy tuple behavior through a compatibility method.
- Modify: `python/nanorole_runtime/src/nanorole_runtime/turns.py`
  Consumes `ContextPackage` and records structured context metadata.
- Modify: `python/nanorole_runtime/src/nanorole_runtime/sessions.py`
  Becomes a thinner facade over stores/services. Existing public methods stay compatible.
- Modify: `python/nanorole_runtime/src/nanorole_runtime/api.py`
  Accepts `roleId` and `mode: "story"` while keeping `role_id` and `mode: "scenario"`.
- Create: `python/nanorole_runtime/tests/test_session_store.py`
  Tests extracted persistence behavior.
- Create: `python/nanorole_runtime/tests/test_story.py`
  Tests optional story service behavior.
- Modify: `python/nanorole_runtime/tests/test_context.py`
  Tests structured context package.
- Modify: `python/nanorole_runtime/tests/test_sessions.py`
  Tests facade compatibility and single-role story mode.
- Modify: `python/nanorole_runtime/tests/test_api.py`
  Tests new request shape and context preview response.
- Create: `packages/demo/src/pages/shared.ts`
  Shared page helpers and layout constants.
- Create: `packages/demo/src/pages/chatPage.ts`
  Chat workbench HTML.
- Create: `packages/demo/src/pages/memoriesPage.ts`
  Memory page HTML.
- Create: `packages/demo/src/pages/logsPage.ts`
  Logs page HTML.
- Modify: `packages/demo/src/pages.ts`
  Re-exports page constants for compatibility.
- Modify: `packages/demo/src/server.ts`
  Imports split pages and keeps existing routes.
- Modify: `packages/demo/tests/server.test.ts`
  Updates smoke tests for single-role workbench copy.

---

### Task 1: Extract Session Store

**Files:**
- Create: `python/nanorole_runtime/src/nanorole_runtime/session_store.py`
- Create: `python/nanorole_runtime/tests/test_session_store.py`
- Modify: `python/nanorole_runtime/src/nanorole_runtime/sessions.py`

- [ ] **Step 1: Write the failing session store test**

Add `python/nanorole_runtime/tests/test_session_store.py`:

```python
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
```

- [ ] **Step 2: Run the focused test and confirm it fails**

Run:

```powershell
uv run pytest tests/test_session_store.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'nanorole_runtime.session_store'`.

- [ ] **Step 3: Create `SessionStore`**

Create `python/nanorole_runtime/src/nanorole_runtime/session_store.py` with:

```python
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .sessions_types import ChatMessage
from .storage import Database


VALID_SESSION_STATUS = {"active", "archived", "deleted"}


@dataclass
class StoredSession:
    session_id: str
    role_id: str
    role_name: str
    role_version: str
    mode: str
    companion_id: str
    scenario_id: str | None = None
    scenario_name: str | None = None
    title: str | None = None
    status: str = "active"
    created_at: str | None = None
    updated_at: str | None = None
    last_message_at: str | None = None
    history: list[ChatMessage] = field(default_factory=list)


class SessionStore:
    def __init__(self, database: Database) -> None:
        self.database = database

    def create_session(
        self,
        *,
        user_id: str,
        companion_id: str,
        role_id: str,
        role_name: str,
        role_version: str,
        mode: str,
        scenario_id: str | None,
        scenario_name: str | None,
    ) -> StoredSession:
        now = _now()
        session_id = uuid.uuid4().hex
        with self.database.connect() as connection:
            connection.execute(
                """
                insert into users (id, display_name, created_at, updated_at)
                values (?, ?, ?, ?)
                on conflict(id) do update set updated_at = excluded.updated_at
                """,
                (user_id, "Local User", now, now),
            )
            connection.execute(
                """
                insert into companions (id, role_id, role_version, display_name, created_at, updated_at)
                values (?, ?, ?, ?, ?, ?)
                on conflict(id) do update set
                  role_version = excluded.role_version,
                  display_name = excluded.display_name,
                  updated_at = excluded.updated_at
                """,
                (companion_id, role_id, role_version, role_name, now, now),
            )
            connection.execute(
                """
                insert into sessions (
                  id, user_id, companion_id, role_id, role_name, role_version, mode, scenario_id, scenario_name,
                  title, status, created_at, updated_at, last_message_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    user_id,
                    companion_id,
                    role_id,
                    role_name,
                    role_version,
                    mode,
                    scenario_id,
                    scenario_name,
                    None,
                    "active",
                    now,
                    now,
                    None,
                ),
            )
        return self.get_session(session_id)

    def get_session(self, session_id: str) -> StoredSession:
        row = self.database.fetch_one("select * from sessions where id = ? and status != 'deleted'", (session_id,))
        if row is None:
            raise KeyError(session_id)
        return self._session_from_row(row, include_history=True)

    def list_sessions(self) -> list[StoredSession]:
        rows = self.database.fetch_all(
            """
            select *
            from sessions
            where status != 'deleted'
            order by coalesce(last_message_at, created_at) desc, created_at desc
            """
        )
        return [self._session_from_row(row, include_history=True) for row in rows]

    def update_session(self, session_id: str, *, title: str | None, status: str | None) -> StoredSession:
        current = self.get_session(session_id)
        next_title = title if title is not None else current.title
        next_status = status if status is not None else current.status
        if next_status not in VALID_SESSION_STATUS:
            raise ValueError(f"invalid session status: {next_status}")
        now = _now()
        self.database.execute(
            """
            update sessions
            set title = ?, status = ?, updated_at = ?
            where id = ?
            """,
            (next_title, next_status, now, session_id),
        )
        return self.get_session(session_id)

    def persist_message(
        self,
        session_id: str,
        role: str,
        content: str,
        *,
        speaker_id: str | None = None,
        input_modality: str | None = None,
        output_modality: str | None = None,
        emotion_label: str | None = None,
        audio_ref: str | None = None,
    ) -> ChatMessage:
        now = _now()
        message_id = uuid.uuid4().hex
        with self.database.connect() as connection:
            row = connection.execute(
                "select coalesce(max(ordinal), -1) + 1 as ordinal from messages where session_id = ?",
                (session_id,),
            ).fetchone()
            ordinal = int(row["ordinal"])
            connection.execute(
                """
                insert into messages (
                  id, session_id, role, content, created_at, ordinal,
                  speaker_id, input_modality, output_modality, emotion_label, audio_ref
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message_id,
                    session_id,
                    role,
                    content,
                    now,
                    ordinal,
                    _clean_optional(speaker_id),
                    _clean_optional(input_modality),
                    _clean_optional(output_modality),
                    _clean_optional(emotion_label),
                    _clean_optional(audio_ref),
                ),
            )
            connection.execute(
                """
                update sessions
                set updated_at = ?, last_message_at = ?
                where id = ?
                """,
                (now, now, session_id),
            )
        return ChatMessage(
            message_id=message_id,
            role=role,
            content=content,
            speaker_id=_clean_optional(speaker_id),
            input_modality=_clean_optional(input_modality),
            output_modality=_clean_optional(output_modality),
            emotion_label=_clean_optional(emotion_label),
            audio_ref=_clean_optional(audio_ref),
        )

    def load_messages(self, session_id: str) -> list[ChatMessage]:
        rows = self.database.fetch_all(
            """
            select id, role, content, speaker_id, input_modality, output_modality, emotion_label, audio_ref
            from messages
            where session_id = ?
            order by ordinal
            """,
            (session_id,),
        )
        return [
            ChatMessage(
                message_id=str(row["id"]),
                role=str(row["role"]),
                content=str(row["content"]),
                speaker_id=str(row["speaker_id"]) if row["speaker_id"] is not None else None,
                input_modality=str(row["input_modality"]) if row["input_modality"] is not None else None,
                output_modality=str(row["output_modality"]) if row["output_modality"] is not None else None,
                emotion_label=str(row["emotion_label"]) if row["emotion_label"] is not None else None,
                audio_ref=str(row["audio_ref"]) if row["audio_ref"] is not None else None,
            )
            for row in rows
        ]

    def record_event(self, session_id: str, event_type: str, payload: dict[str, Any]) -> None:
        self.database.execute(
            """
            insert into session_events (id, session_id, type, payload_json, created_at)
            values (?, ?, ?, ?, ?)
            """,
            (uuid.uuid4().hex, session_id, event_type, json.dumps(payload, ensure_ascii=False, sort_keys=True), _now()),
        )

    def load_events(self, session_id: str) -> list[dict[str, Any]]:
        rows = self.database.fetch_all(
            """
            select id, session_id, type, payload_json, created_at
            from session_events
            where session_id = ?
            order by created_at
            """,
            (session_id,),
        )
        return [
            {
                "eventId": str(row["id"]),
                "sessionId": str(row["session_id"]),
                "type": str(row["type"]),
                "payload": json.loads(str(row["payload_json"])),
                "createdAt": str(row["created_at"]),
            }
            for row in rows
        ]

    def _session_from_row(self, row: Any, *, include_history: bool) -> StoredSession:
        session_id = str(row["id"])
        return StoredSession(
            session_id=session_id,
            role_id=str(row["role_id"]),
            role_name=str(row["role_name"]),
            role_version=str(row["role_version"]),
            mode=str(row["mode"]),
            companion_id=str(row["companion_id"]),
            scenario_id=str(row["scenario_id"]) if row["scenario_id"] is not None else None,
            scenario_name=str(row["scenario_name"]) if row["scenario_name"] is not None else None,
            title=str(row["title"]) if row["title"] is not None else None,
            status=str(row["status"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
            last_message_at=str(row["last_message_at"]) if row["last_message_at"] is not None else None,
            history=self.load_messages(session_id) if include_history else [],
        )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None
```

- [ ] **Step 4: Wire `SessionManager` to use `SessionStore` without changing responses**

In `sessions.py`, initialize `self.session_store = SessionStore(self.database)`.

Replace `_persist_message`, `_load_messages`, and the SQL body of `_persist_session` with calls to `self.session_store`. Keep method names as wrappers so existing code continues to call them:

```python
def _persist_message(self, session_id: str, role: str, content: str, **metadata) -> ChatMessage:
    message = self.session_store.persist_message(session_id, role, content, **metadata)
    if session_id in self._sessions:
        self._sessions[session_id].updated_at = self._now()
        self._sessions[session_id].last_message_at = self._now()
    return message

def _load_messages(self, session_id: str) -> list[ChatMessage]:
    return self.session_store.load_messages(session_id)
```

Use `self.session_store.create_session(user_id=DEFAULT_USER_ID, companion_id=role.id, role_id=role.id, role_name=role.name, role_version=role.version, mode=session.mode, scenario_id=session.scenario_id, scenario_name=session.scenario_name)` inside `create_session()` and `create_scenario_session()` only after tests pass with the wrapper extraction.

- [ ] **Step 5: Run session store and session tests**

Run:

```powershell
uv run pytest tests/test_session_store.py tests/test_sessions.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add python/nanorole_runtime/src/nanorole_runtime/session_store.py python/nanorole_runtime/src/nanorole_runtime/sessions.py python/nanorole_runtime/tests/test_session_store.py
git commit -m "refactor: extract session store"
```

---

### Task 2: Extract Optional Story Service

**Files:**
- Create: `python/nanorole_runtime/src/nanorole_runtime/story.py`
- Create: `python/nanorole_runtime/tests/test_story.py`
- Modify: `python/nanorole_runtime/src/nanorole_runtime/sessions.py`

- [ ] **Step 1: Write failing story service tests**

Add `python/nanorole_runtime/tests/test_story.py`:

```python
from pathlib import Path

from nanorole_runtime.scenarios import ScenarioPackage
from nanorole_runtime.story import StoryService
from nanorole_runtime.storage import Database


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
    event = service.append_event(
        "s1",
        "clue_revealed",
        {"clueId": "clue-1", "summary": "The brass key was found."},
    )
    state = service.get_state("s1")
    context = service.visible_context("s1")

    assert event["ordinal"] == 0
    assert state["currentScene"] == "The observatory clock has stopped."
    assert state["revealedClues"][0]["content"] == "A bent brass key rests under the dial."
    assert context["publicFacts"][0]["content"] == "The public clock stopped at midnight."
    assert context["revealedClues"][0]["id"] == "clue-1"
    assert "hiddenFacts" not in context
    assert "The clock was stopped from inside." not in str(context)
```

- [ ] **Step 2: Run the focused test and confirm it fails**

Run:

```powershell
uv run pytest tests/test_story.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'nanorole_runtime.story'`.

- [ ] **Step 3: Implement `StoryService` by moving existing session helpers**

Create `python/nanorole_runtime/src/nanorole_runtime/story.py` with the existing logic currently in `SessionManager._persist_story_state`, `_apply_story_event_to_state`, `_load_scene_events`, and `_visible_story_context`.

The public methods must have these concrete signatures:

- `__init__(self, database: Database) -> None`
- `create_story_state(self, session_id: str, scenario: ScenarioPackage) -> None`
- `get_state(self, session_id: str) -> dict[str, Any]`
- `append_event(self, session_id: str, event_type: str, payload: dict[str, Any]) -> dict[str, Any]`
- `visible_context(self, session_id: str) -> dict[str, Any]`

`visible_context()` returns only:

```python
{
    "currentScene": state["currentScene"],
    "currentState": state["currentState"],
    "publicFacts": state["publicFacts"],
    "revealedClues": state["revealedClues"],
    "recentEvents": state["recentEvents"],
}
```

- [ ] **Step 4: Wire `SessionManager` to `StoryService`**

In `SessionManager.__init__`:

```python
self.story_service = StoryService(self.database)
```

Replace:

```python
self._persist_story_state(session.session_id, scenario, now)
```

with:

```python
self.story_service.create_story_state(session.session_id, scenario)
```

Replace `get_story_state()`, `append_story_event()`, and `_visible_story_context()` bodies with calls to `self.story_service`.

- [ ] **Step 5: Run story and session tests**

Run:

```powershell
uv run pytest tests/test_story.py tests/test_sessions.py tests/test_api.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add python/nanorole_runtime/src/nanorole_runtime/story.py python/nanorole_runtime/src/nanorole_runtime/sessions.py python/nanorole_runtime/tests/test_story.py
git commit -m "refactor: extract optional story service"
```

---

### Task 3: Add Structured Context Package

**Files:**
- Modify: `python/nanorole_runtime/src/nanorole_runtime/context.py`
- Modify: `python/nanorole_runtime/src/nanorole_runtime/turns.py`
- Modify: `python/nanorole_runtime/src/nanorole_runtime/sessions.py`
- Modify: `python/nanorole_runtime/tests/test_context.py`
- Modify: `python/nanorole_runtime/tests/test_sessions.py`

- [ ] **Step 1: Write failing context package tests**

Append to `python/nanorole_runtime/tests/test_context.py`:

```python
def test_context_package_exposes_structured_inputs(tmp_path: Path) -> None:
    database = Database(tmp_path / "nanorole.sqlite3")
    database.initialize()
    store = MemoryStore(database)
    memory = store.create_memory(
        user_id="local-user",
        companion_id="companion",
        memory_type="preference",
        content="The user prefers concise explanations.",
        importance=0.8,
        confidence=0.9,
        source_message_ids=["m1"],
    )
    store.upsert_relationship_state(
        user_id="local-user",
        companion_id="companion",
        summary="The user trusts concise technical guidance.",
        familiarity=0.4,
        trust=0.5,
        preferred_address="",
        communication_style="concise",
    )

    assembler = ContextAssembler(memory_store=store)
    package = assembler.build_context_package(
        session_id="s1",
        mode="companion",
        role=role(),
        user_id="local-user",
        companion_id="companion",
        history=[ChatMessage(role="user", content="Keep this short.")],
        user_input="Explain the plan concisely.",
        session_summary="The user is planning Nanorole.",
        story_context=None,
    )

    assert package.session_id == "s1"
    assert package.mode == "companion"
    assert package.world_context == "A quiet room."
    assert package.relationship is not None
    assert package.relationship.communication_style == "concise"
    assert [item.memory_id for item in package.selected_memories] == [memory.memory_id]
    assert package.session_summary == "The user is planning Nanorole."
    assert package.story is None
    assert package.model_messages[-1] == {"role": "user", "content": "Explain the plan concisely."}
```

- [ ] **Step 2: Run context tests and confirm failure**

Run:

```powershell
uv run pytest tests/test_context.py -q
```

Expected: FAIL with `AttributeError: 'ContextAssembler' object has no attribute 'build_context_package'`.

- [ ] **Step 3: Add `ContextPackage` dataclass and builder**

In `context.py`, add:

```python
@dataclass(frozen=True)
class ContextPackage:
    session_id: str
    mode: str
    role: RolePackage
    world_context: str
    relationship: RelationshipState | None
    selected_memories: list[MemoryRecord]
    session_summary: str | None
    recent_messages: list[ChatMessage]
    story: dict[str, Any] | None
    model_messages: list[dict[str, str]]
```

Add `ContextAssembler.build_context_package` with the same retrieval and prompt assembly behavior currently inside `build_messages()`. It must accept `session_id`, `mode`, `role`, `user_id`, `companion_id`, `history`, `user_input`, `session_summary`, and `story_context`.

Keep `build_messages()` as a compatibility wrapper:

```python
def build_messages(self, *, role: RolePackage, user_id: str, companion_id: str, history: list[ChatMessage], user_input: str, session_summary: str | None = None, story_context: dict[str, Any] | None = None) -> tuple[list[dict[str, str]], list[MemoryRecord]]:
    package = self.build_context_package(
        session_id="",
        mode="companion" if story_context is None else "story",
        role=role,
        user_id=user_id,
        companion_id=companion_id,
        history=history,
        user_input=user_input,
        session_summary=session_summary,
        story_context=story_context,
    )
    return package.model_messages, package.selected_memories
```

- [ ] **Step 4: Update `CompanionTurnPipeline` to use `build_context_package`**

In `turns.py`, replace:

```python
messages, used_memories = assembler.build_messages(
    role=self.role,
    user_id=self.user_id,
    companion_id=self.companion_id,
    history=self.history[:-1],
    user_input=user_input,
    session_summary=self.session_summary,
    story_context=self.story_context,
)
```

with:

```python
context_package = assembler.build_context_package(
    session_id=self.session_id,
    mode="story" if self.story_context else "companion",
    role=self.role,
    user_id=self.user_id,
    companion_id=self.companion_id,
    history=self.history[:-1],
    user_input=user_input,
    session_summary=self.session_summary,
    story_context=self.story_context,
)
messages = context_package.model_messages
used_memories = context_package.selected_memories
```

Record context metadata:

```python
"context": {
    "world_chars": len(context_package.world_context),
    "memory_count": len(context_package.selected_memories),
    "has_relationship": context_package.relationship is not None,
    "has_session_summary": bool(context_package.session_summary),
    "has_story": context_package.story is not None,
}
```

- [ ] **Step 5: Update `SessionManager.preview_context`**

Return both legacy and structured fields:

```python
return {
    "sessionId": session.session_id,
    "mode": session.mode,
    "messages": package.model_messages,
    "systemPrompt": package.model_messages[0]["content"],
    "context": {
        "world": package.world_context,
        "relationship": _relationship_response(package.relationship),
        "selectedMemories": [_memory_context_response(memory) for memory in package.selected_memories],
        "sessionSummary": package.session_summary,
        "story": package.story,
    },
    "usedMemories": [
        {
            "memoryId": memory.memory_id,
            "type": memory.type,
            "content": memory.content,
            "importance": memory.importance,
            "confidence": memory.confidence,
        }
        for memory in package.selected_memories
    ],
    "usedStory": package.story,
}
```

- [ ] **Step 6: Run context/session/API tests**

Run:

```powershell
uv run pytest tests/test_context.py tests/test_sessions.py tests/test_api.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add python/nanorole_runtime/src/nanorole_runtime/context.py python/nanorole_runtime/src/nanorole_runtime/turns.py python/nanorole_runtime/src/nanorole_runtime/sessions.py python/nanorole_runtime/tests/test_context.py python/nanorole_runtime/tests/test_sessions.py
git commit -m "feat: add structured context package"
```

---

### Task 4: Add Single-Role Request Shape And Story Alias

**Files:**
- Modify: `python/nanorole_runtime/src/nanorole_runtime/api.py`
- Modify: `python/nanorole_runtime/src/nanorole_runtime/sessions.py`
- Modify: `python/nanorole_runtime/tests/test_api.py`
- Modify: `python/nanorole_runtime/tests/test_sessions.py`

- [ ] **Step 1: Write failing API compatibility tests**

Append to `python/nanorole_runtime/tests/test_api.py`:

```python
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
```

- [ ] **Step 2: Run API tests and confirm failure**

Run:

```powershell
uv run pytest tests/test_api.py -q
```

Expected: FAIL because `CreateSessionRequest` has no `roleId` and `mode: "story"` is invalid.

- [ ] **Step 3: Extend request model**

In `api.py`, change `CreateSessionRequest`:

```python
class CreateSessionRequest(BaseModel):
    role_id: str | None = None
    roleId: str | None = None
    mode: str = "companion"
    scenarioId: str | None = None
    roleIds: list[str] | None = None
```

In `create_session()`, resolve:

```python
requested_role_id = request.role_id or request.roleId
```

Use `requested_role_id` for companion creation.

- [ ] **Step 4: Add story alias in `SessionManager`**

Add:

```python
def create_story_session(self, *, role_id: str, scenario_id: str | None = None) -> SessionState:
    if scenario_id:
        session = self.create_scenario_session(scenario_id, role_ids=[role_id])
        session.mode = "story"
        self.database.execute("update sessions set mode = ? where id = ?", ("story", session.session_id))
        return self.get_session(session.session_id)
    return self.create_session(role_id)
```

This keeps first implementation conservative: story mode is an alias around existing scenario state when a scenario is supplied, and otherwise falls back to a normal companion session.

- [ ] **Step 5: Route `mode: "story"`**

In `api.py`:

```python
elif request.mode == "story":
    if not requested_role_id:
        raise ValueError("roleId is required for story sessions")
    session = manager.create_story_session(role_id=requested_role_id, scenario_id=request.scenarioId)
```

- [ ] **Step 6: Run API/session tests**

Run:

```powershell
uv run pytest tests/test_api.py tests/test_sessions.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add python/nanorole_runtime/src/nanorole_runtime/api.py python/nanorole_runtime/src/nanorole_runtime/sessions.py python/nanorole_runtime/tests/test_api.py python/nanorole_runtime/tests/test_sessions.py
git commit -m "feat: add single-role story session alias"
```

---

### Task 5: Split Demo Pages Without Changing Routes

**Files:**
- Create: `packages/demo/src/pages/shared.ts`
- Create: `packages/demo/src/pages/chatPage.ts`
- Create: `packages/demo/src/pages/memoriesPage.ts`
- Create: `packages/demo/src/pages/logsPage.ts`
- Modify: `packages/demo/src/pages.ts`
- Modify: `packages/demo/src/server.ts`
- Modify: `packages/demo/tests/server.test.ts`

- [ ] **Step 1: Write failing page split smoke test**

Append to `packages/demo/tests/server.test.ts`:

```ts
test("chat page presents single-role studio as the default workbench", async () => {
  const demo = createDemoServer({ projectRoot: process.cwd(), runtimeUrl: "http://127.0.0.1:9" });
  const baseUrl = await listen(demo);

  const html = await fetch(`${baseUrl}/chat`).then((response) => response.text());

  expect(html).toContain("Nanorole Studio");
  expect(html).toContain("Relationship");
  expect(html).toContain("World");
  expect(html).toContain("Memory");
  expect(html).toContain("Context");
  expect(html).not.toContain("multi-role");
});
```

- [ ] **Step 2: Run demo tests and confirm failure**

Run:

```powershell
corepack yarn workspace @nanorole/demo test --run
```

Expected: FAIL because the current page title is `Nanorole Chat` and the inspector labels are missing.

- [ ] **Step 3: Split page modules**

Move the existing constants exactly. Do this as a mechanical split, without editing template contents during the move:

```ts
// packages/demo/src/pages/chatPage.ts
// Contains the complete `export const CHAT_HTML` template string currently in `packages/demo/src/pages.ts`, from its export line through its closing template backtick and semicolon.

// packages/demo/src/pages/memoriesPage.ts
// Contains the complete `export const MEMORIES_HTML` template string currently in `packages/demo/src/pages.ts`, from its export line through its closing template backtick and semicolon.

// packages/demo/src/pages/logsPage.ts
// Contains the complete `export const LOGS_HTML` template string currently in `packages/demo/src/pages.ts`, from its export line through its closing template backtick and semicolon.
```

Then replace `packages/demo/src/pages.ts` with:

```ts
export { CHAT_HTML } from "./pages/chatPage.js";
export { LOGS_HTML } from "./pages/logsPage.js";
export { MEMORIES_HTML } from "./pages/memoriesPage.js";
```

- [ ] **Step 4: Rename chat shell to Nanorole Studio**

In `chatPage.ts`, update visible labels only:

```html
<title>Nanorole Studio</title>
<h1>Nanorole Studio</h1>
```

Add right inspector placeholders in the existing sidebar/detail area:

```html
<div class="detail" id="world-detail">World context will appear here.</div>
<div class="detail" id="relationship-detail">Relationship state will appear here.</div>
<div class="detail" id="memory-detail">Selected memories will appear here.</div>
<div class="detail" id="context-detail">Context preview is available after session creation.</div>
```

Keep IDs already referenced by JavaScript. If replacing `story-detail`, update every reference in `chatPage.ts` to use the new container that still exists.

- [ ] **Step 5: Run demo tests**

Run:

```powershell
corepack yarn workspace @nanorole/demo test --run
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add packages/demo/src/pages.ts packages/demo/src/pages/shared.ts packages/demo/src/pages/chatPage.ts packages/demo/src/pages/memoriesPage.ts packages/demo/src/pages/logsPage.ts packages/demo/src/server.ts packages/demo/tests/server.test.ts
git commit -m "refactor: split demo page modules"
```

---

### Task 6: Add Workbench Context Inspector Data Flow

**Files:**
- Modify: `packages/demo/src/pages/chatPage.ts`
- Modify: `packages/demo/tests/server.test.ts`
- Modify: `python/nanorole_runtime/tests/test_api.py`

- [ ] **Step 1: Extend API test for structured context preview**

In `python/nanorole_runtime/tests/test_api.py`, add assertions to the existing context preview test:

```python
assert preview.json()["mode"] == "companion"
assert preview.json()["systemPrompt"]
assert preview.json()["context"]["world"] == "A city of brass towers."
assert "selectedMemories" in preview.json()["context"]
assert "sessionSummary" in preview.json()["context"]
assert "story" in preview.json()["context"]
```

- [ ] **Step 2: Run API tests and confirm failure if Task 3 did not wire response**

Run:

```powershell
uv run pytest tests/test_api.py -q
```

Expected: PASS if Task 3 already added fields; otherwise FAIL and wire the response from Task 3.

- [ ] **Step 3: Add chat page context loading**

In `chatPage.ts`, add:

```js
async function loadContextPreview() {
  if (!sessionId) return;
  try {
    const response = await fetch("/api/sessions/" + encodeURIComponent(sessionId) + "/context-preview", { cache: "no-store" });
    const data = await response.json();
    const context = data.context || {};
    document.querySelector("#world-detail").textContent = context.world || "-";
    document.querySelector("#relationship-detail").textContent = context.relationship ? JSON.stringify(context.relationship, null, 2) : "-";
    document.querySelector("#memory-detail").textContent = Array.isArray(context.selectedMemories)
      ? context.selectedMemories.map((item) => "[" + item.type + "] " + item.content).join("\\n")
      : "-";
    document.querySelector("#context-detail").textContent = data.systemPrompt || "-";
  } catch (error) {
    document.querySelector("#context-detail").textContent = String(error);
  }
}
```

Call `await loadContextPreview()` after `startSession()`, `resumeSession()`, and `sendMessage()` completion.

- [ ] **Step 4: Update demo smoke test**

In `packages/demo/tests/server.test.ts`, assert:

```ts
expect(html).toContain("async function loadContextPreview");
expect(html).toContain('id="relationship-detail"');
expect(html).toContain('id="world-detail"');
expect(html).toContain('id="memory-detail"');
expect(html).toContain('id="context-detail"');
```

- [ ] **Step 5: Run Python and demo tests**

Run:

```powershell
uv run pytest tests/test_api.py -q
corepack yarn workspace @nanorole/demo test --run
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add python/nanorole_runtime/tests/test_api.py packages/demo/src/pages/chatPage.ts packages/demo/tests/server.test.ts
git commit -m "feat: show context inspector in workbench"
```

---

### Task 7: Regression Verification

**Files:**
- No source edits.

- [ ] **Step 1: Run full Python tests**

Run:

```powershell
uv run pytest
```

Expected: `75 passed` or higher, depending on newly added tests.

- [ ] **Step 2: Run full TypeScript tests**

Run:

```powershell
corepack yarn test
```

Expected: all CLI and demo tests pass.

- [ ] **Step 3: Run TypeScript build**

Run:

```powershell
corepack yarn build
```

Expected: all workspaces build successfully.

- [ ] **Step 4: Check whitespace and status**

Run:

```powershell
git diff --check
git status --short --branch
```

Expected: no whitespace errors; working tree only contains intentional committed or staged changes.

---

## Self-Review

- The plan keeps current API behavior compatible.
- The plan does not require multi-role, director, turn order, voting, or hidden knowledge separation.
- Story mode is optional and single-role.
- The first implementation batch produces testable runtime boundaries before deeper UI work.
- No task requires a destructive database migration.
