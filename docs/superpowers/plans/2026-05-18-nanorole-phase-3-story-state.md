# Nanorole Phase 3 Story State Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make scenario story state durable, event-driven, inspectable through runtime APIs, and visible in model context without leaking hidden facts.

**Architecture:** Keep Phase 2 scenario sessions intact and add a small `scene_events` table plus `SessionManager.append_story_event`. Story state remains a JSON document in `story_states` for Phase 3, with `currentState`, public facts, hidden facts, clues, and recent events exposed through API responses. Context assembly receives a sanitized story context containing current scene, public facts, revealed clues, and recent events, but not hidden facts.

**Tech Stack:** Python 3.12, FastAPI, SQLite migrations, pytest, TypeScript demo proxy tests, Vitest.

---

### Task 1: Story Event Persistence

**Files:**
- Modify: `python/nanorole_runtime/src/nanorole_runtime/storage.py`
- Modify: `python/nanorole_runtime/src/nanorole_runtime/sessions.py`
- Modify: `python/nanorole_runtime/tests/test_storage.py`
- Modify: `python/nanorole_runtime/tests/test_sessions.py`

- [ ] Write a failing storage migration test asserting migration `0004_scene_events` creates `scene_events` with `id`, `session_id`, `type`, `payload_json`, `created_at`, and `ordinal`.
- [ ] Write a failing session manager test that creates a scenario session, appends a `state_changed` event with `currentScene` and `statePatch`, and verifies `get_story_state()` returns the updated `currentScene`, `currentState.phase`, and a recent event.
- [ ] Write a failing session manager test that appends a `clue_revealed` event with `clueId` and verifies the matching clue status becomes `revealed`.
- [ ] Run `uv run pytest tests/test_storage.py tests/test_sessions.py -q` and confirm the new tests fail.
- [ ] Implement migration `0004_scene_events`.
- [ ] Implement `SessionManager.append_story_event(session_id, event_type, payload)` and helpers to load/update the story state JSON.
- [ ] Run `uv run pytest tests/test_storage.py tests/test_sessions.py -q` and confirm the tests pass.

### Task 2: Story Event Runtime API

**Files:**
- Modify: `python/nanorole_runtime/src/nanorole_runtime/api.py`
- Modify: `python/nanorole_runtime/tests/test_api.py`

- [ ] Write a failing API test that posts to `POST /v1/sessions/{sessionId}/events` with `{ "type": "state_changed", "payload": { "statePatch": { "phase": "investigation" } } }`.
- [ ] Assert the response contains an `eventId`, `type`, and `ordinal`.
- [ ] Assert `GET /v1/sessions/{sessionId}/story-state` includes `currentState.phase == "investigation"` and the recent event.
- [ ] Run `uv run pytest tests/test_api.py -q` and confirm the test fails.
- [ ] Add `AppendStoryEventRequest` and the runtime route.
- [ ] Run `uv run pytest tests/test_api.py -q` and confirm the test passes.

### Task 3: Story Context Preview

**Files:**
- Modify: `python/nanorole_runtime/src/nanorole_runtime/context.py`
- Modify: `python/nanorole_runtime/src/nanorole_runtime/turns.py`
- Modify: `python/nanorole_runtime/src/nanorole_runtime/sessions.py`
- Modify: `python/nanorole_runtime/tests/test_context.py`
- Modify: `python/nanorole_runtime/tests/test_sessions.py`

- [ ] Write a failing context/session test that creates a scenario session and calls `preview_context`.
- [ ] Assert the system prompt contains `Story state`, current scene, public fact text, revealed clue text, and recent event text.
- [ ] Assert the system prompt does not contain hidden fact content.
- [ ] Assert the preview JSON includes `usedStory.publicFacts`, `usedStory.revealedClues`, and `usedStory.recentEvents`.
- [ ] Run `uv run pytest tests/test_context.py tests/test_sessions.py -q` and confirm the test fails.
- [ ] Extend `ContextAssembler.build_messages(..., story_context=None)` and `_system_prompt` to include sanitized story context.
- [ ] Pass sanitized story context from `SessionManager.preview_context` and `CompanionTurnPipeline`.
- [ ] Run `uv run pytest tests/test_context.py tests/test_sessions.py -q` and confirm the tests pass.

### Task 4: Demo Story Event Proxy

**Files:**
- Modify: `packages/demo/src/server.ts`
- Modify: `packages/demo/tests/server.test.ts`

- [ ] Write a failing demo server test that posts `/api/sessions/s1/events` and asserts the upstream request is `POST /v1/sessions/s1/events` with the same JSON body.
- [ ] Run `corepack yarn workspace @nanorole/demo test --run` and confirm the test fails.
- [ ] Add the proxy route.
- [ ] Run `corepack yarn workspace @nanorole/demo test --run` and confirm the test passes.

### Task 5: Final Verification

**Files:**
- No code edits.

- [ ] Run `uv run pytest` from `python/nanorole_runtime`.
- [ ] Run `corepack yarn test` from repo root.
- [ ] Run `corepack yarn build` from repo root.
- [ ] Run `git diff --check` and `git status --short --branch`.
- [ ] Commit the branch and fast-forward merge to `main` if verification is clean.
