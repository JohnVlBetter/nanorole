# Nanorole Phase 2 Scenario Package Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the first scenario package slice so the runtime and demo can list scenarios and create a scenario-backed session without breaking companion sessions.

**Architecture:** Add a Python `scenarios.py` loader parallel to `roles.py`, with strict YAML validation and camelCase API serialization at the FastAPI boundary. Persist scenario sessions with minimal session metadata, participants, and initial story state so Phase 3 can extend state/event APIs without reworking Phase 2 data. Keep chat streaming single-role for now by using the first scenario role as the active companion role.

**Tech Stack:** Python 3.12, FastAPI, SQLite migrations, PyYAML, pytest, TypeScript demo server, Vitest.

---

### Task 1: Scenario Package Loader

**Files:**
- Create: `python/nanorole_runtime/src/nanorole_runtime/scenarios.py`
- Create: `python/nanorole_runtime/tests/test_scenarios.py`
- Create: `examples/scenarios/forgotten-observatory/scenario.yaml`
- Modify: `python/nanorole_runtime/src/nanorole_runtime/config.py`

- [ ] Write a failing loader test that creates `examples/scenarios/forgotten-observatory/scenario.yaml`, calls `load_scenario_by_id`, and asserts these fields:

```python
assert scenario.id == "forgotten-observatory"
assert scenario.mode == "mystery"
assert scenario.roles == ["clockwork-sage", "neko-maid"]
assert scenario.initial_state["phase"] == "opening"
assert scenario.public_facts[0]["id"] == "public-1"
assert scenario.hidden_facts[0]["visibility"] == ["clockwork-sage"]
assert scenario.clues[0]["status"] == "hidden"
```

- [ ] Write a failing loader test that `list_scenarios(root)` returns summaries ordered by scenario id and excludes malformed scenario directories.
- [ ] Write a failing validation test that missing `initial_scene` raises `ScenarioValidationError` with `scenario.yaml missing required fields: initial_scene`.
- [ ] Run `uv run pytest tests/test_scenarios.py -q` from `python/nanorole_runtime` and confirm it fails because `nanorole_runtime.scenarios` does not exist.
- [ ] Implement `ScenarioPackage`, `ScenarioSummary`, `ScenarioValidationError`, `ScenarioNotFoundError`, `load_scenario_package`, `load_scenario_by_id`, and `list_scenarios`.
- [ ] Add `scenarios_dir: Path` to `PathsConfig` and default it to `examples/scenarios` in `load_config`.
- [ ] Add `examples/scenarios/forgotten-observatory/scenario.yaml` using existing role ids `clockwork-sage` and `neko-maid`.
- [ ] Run `uv run pytest tests/test_scenarios.py tests/test_config.py -q` and confirm the tests pass.

### Task 2: Scenario Session Storage

**Files:**
- Modify: `python/nanorole_runtime/src/nanorole_runtime/storage.py`
- Modify: `python/nanorole_runtime/src/nanorole_runtime/sessions.py`
- Modify: `python/nanorole_runtime/tests/test_storage.py`
- Modify: `python/nanorole_runtime/tests/test_sessions.py`

- [ ] Write a failing storage migration test that initializes an old database and asserts:

```python
assert {"mode", "scenario_id"} <= table_columns("sessions")
assert {"session_id", "role_id", "display_name", "ordinal"} <= table_columns("session_participants")
assert {"session_id", "scenario_id", "state_json", "current_scene"} <= table_columns("story_states")
```

- [ ] Write a failing session manager test that creates a scenario session and asserts:

```python
session.mode == "scenario"
session.scenario_id == "forgotten-observatory"
session.role_id == "clockwork-sage"
assert [participant["roleId"] for participant in session.participants] == ["clockwork-sage", "neko-maid"]
state = manager.get_story_state(session.session_id)
assert state["scenarioId"] == "forgotten-observatory"
assert state["currentScene"] == "The observatory clock has stopped..."
```

- [ ] Run `uv run pytest tests/test_storage.py tests/test_sessions.py -q` and confirm the new tests fail for missing session metadata/state behavior.
- [ ] Add a migration `0003_scenario_sessions` that adds `sessions.mode`, `sessions.scenario_id`, `session_participants`, and `story_states`.
- [ ] Extend `SessionState` with `mode`, `scenario_id`, `scenario_name`, and `participants`.
- [ ] Add `SessionManager.create_scenario_session(scenario_id, role_ids=None)` that loads the scenario, validates roles exist, uses the first role as the active companion role, persists participants in scenario order, and writes initial story state JSON.
- [ ] Add `SessionManager.get_story_state(session_id)` for internal/API use.
- [ ] Run `uv run pytest tests/test_storage.py tests/test_sessions.py -q` and confirm the tests pass.

### Task 3: Runtime Scenario API

**Files:**
- Modify: `python/nanorole_runtime/src/nanorole_runtime/api.py`
- Modify: `python/nanorole_runtime/tests/test_api.py`

- [ ] Write failing API tests for:

```python
client.get("/v1/scenarios").json()["scenarios"][0]["scenarioId"]
client.get("/v1/scenarios/forgotten-observatory").json()["initialScene"]
client.post("/v1/sessions", json={"mode": "scenario", "scenarioId": "forgotten-observatory"}).json()["mode"]
client.get(f"/v1/sessions/{session_id}").json()["participants"][0]["roleId"]
client.get(f"/v1/sessions/{session_id}/story-state").json()["initialState"]["phase"]
```

- [ ] Write a failing compatibility assertion that `POST /v1/sessions {"role_id": "clockwork-sage"}` still returns a companion session with `mode == "companion"`.
- [ ] Run `uv run pytest tests/test_api.py -q` and confirm the tests fail because scenario endpoints and request fields do not exist.
- [ ] Add `GET /v1/scenarios` and `GET /v1/scenarios/{scenario_id}` using `list_scenarios` and `load_scenario_by_id`.
- [ ] Extend `CreateSessionRequest` to accept `mode`, `scenarioId`, `roleIds`, and old `role_id`.
- [ ] Route scenario create requests to `SessionManager.create_scenario_session`; keep old companion create behavior unchanged.
- [ ] Add `GET /v1/sessions/{session_id}/story-state`.
- [ ] Include `mode`, `scenarioId`, `scenarioName`, and `participants` in session summary/detail responses.
- [ ] Run `uv run pytest tests/test_api.py -q` and confirm the tests pass.

### Task 4: Demo Scenario Proxy

**Files:**
- Modify: `packages/demo/src/server.ts`
- Modify: `packages/demo/tests/server.test.ts`

- [ ] Write a failing demo server test that requests `/api/scenarios` and `/api/scenarios/forgotten-observatory`, then asserts the upstream runtime saw:

```ts
[
  "GET /v1/scenarios",
  "GET /v1/scenarios/forgotten-observatory"
]
```

- [ ] Write a failing demo server test that posts `{ mode: "scenario", scenarioId: "forgotten-observatory" }` to `/api/sessions` and asserts the same JSON body reaches `/v1/sessions`.
- [ ] Run `corepack yarn workspace @nanorole/demo test --run` and confirm the new tests fail for missing proxy routes if the route is absent.
- [ ] Add proxy routes for `GET /api/scenarios` and `GET /api/scenarios/:scenarioId`.
- [ ] Run `corepack yarn workspace @nanorole/demo test --run` and confirm the tests pass.

### Task 5: Final Verification

**Files:**
- No code edits.

- [ ] Run `uv run pytest` from `python/nanorole_runtime`.
- [ ] Run `corepack yarn test` from the repo root.
- [ ] Run `corepack yarn build` from the repo root.
- [ ] Run `git status --short --branch` and `git diff --stat`.
- [ ] Summarize changed files and verification evidence.
