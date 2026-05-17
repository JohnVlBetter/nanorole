# Nanorole Phase 0/1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the next executable roadmap slice: SQLite migrations, companion behavior regression coverage, a reusable companion turn pipeline, message metadata fields, and small workbench debug/readability cleanup.

**Architecture:** Keep the existing single-role companion API compatible while moving schema creation to explicit migrations. Add optional message metadata at the storage/API boundary and route chat turns through a small pipeline that records context, model, memory, summary, and completion events.

**Tech Stack:** Python 3.12, FastAPI, SQLite, pytest, TypeScript demo server, Vitest.

---

### Task 1: Migration And Message Metadata Tests

**Files:**
- Modify: `python/nanorole_runtime/tests/test_storage.py`
- Modify: `python/nanorole_runtime/tests/test_api.py`

- [ ] Write failing tests that initialize an old database, run `Database.initialize()`, assert `schema_migrations` exists, assert message metadata columns were added, and assert initialization is idempotent.
- [ ] Write failing API tests that old `POST /v1/sessions { "role_id": ... }` still works and `GET /v1/sessions/{id}/messages` returns `speakerId`, `inputModality`, `outputModality`, `emotionLabel`, and `audioRef`.
- [ ] Run `uv run pytest tests/test_storage.py tests/test_api.py -q` and confirm the new tests fail for missing migration metadata.

### Task 2: Storage Migration Runner

**Files:**
- Modify: `python/nanorole_runtime/src/nanorole_runtime/storage.py`
- Modify: `python/nanorole_runtime/src/nanorole_runtime/sessions_types.py`
- Modify: `python/nanorole_runtime/src/nanorole_runtime/sessions.py`
- Modify: `python/nanorole_runtime/src/nanorole_runtime/api.py`

- [ ] Replace implicit all-at-once schema setup with a migration runner backed by `schema_migrations`.
- [ ] Keep table creation idempotent for fresh databases.
- [ ] Add nullable message metadata columns: `speaker_id`, `input_modality`, `output_modality`, `emotion_label`, `audio_ref`.
- [ ] Preserve existing message read/write behavior while defaulting user messages to `speakerId=user` and assistant messages to the active role id.
- [ ] Return message metadata in API responses without removing existing fields.

### Task 3: Turn Pipeline And Golden Context Tests

**Files:**
- Create: `python/nanorole_runtime/src/nanorole_runtime/turns.py`
- Modify: `python/nanorole_runtime/src/nanorole_runtime/sessions.py`
- Modify: `python/nanorole_runtime/tests/test_sessions.py`
- Modify: `python/nanorole_runtime/tests/test_context.py`

- [ ] Write failing tests that a streamed companion turn emits durable `turn_started`, `context_built`, `assistant_message`, and `turn_completed` events.
- [ ] Write a context golden test for the current single-role prompt shape.
- [ ] Implement `CompanionTurnPipeline` to cover input persistence, context assembly, model streaming, output persistence, memory extraction scheduling, summary scheduling, and event metadata.
- [ ] Run the focused Python tests until they pass.

### Task 4: Workbench Readability And Debug Tests

**Files:**
- Modify: `python/nanorole_runtime/src/nanorole_runtime/memory.py`
- Modify: `python/nanorole_runtime/tests/test_sessions.py`
- Modify: `packages/demo/src/pages.ts`
- Modify: `packages/demo/tests/server.test.ts`

- [ ] Add a failing test that Chinese “不要记住” skips memory extraction.
- [ ] Replace garbled Chinese policy phrases in `memory.py`.
- [ ] Replace garbled workbench text with readable Chinese labels for chat/log pages.
- [ ] Add demo tests for readable Chinese labels and context/log debug wording.
- [ ] Run `uv run pytest` and `corepack yarn test`.

### Task 5: Final Verification

**Files:**
- No code edits.

- [ ] Run `uv run pytest` from `python/nanorole_runtime`.
- [ ] Run `corepack yarn test` from the repo root.
- [ ] Run `corepack yarn build` from the repo root.
- [ ] Review `git diff --stat` and summarize changed files.
