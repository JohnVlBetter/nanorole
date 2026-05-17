# Companion Memory MVP Design

## Goal

Nanorole should become a long-term emotional companion chat runtime before it expands into game NPCs, multi-character stories, script murder games, Graph RAG, or external chat adapters.

The first product-grade target is:

> A user chats with one companion role over many sessions. The companion remembers stable user facts, preferences, important events, relationship progress, and explicit boundaries. The user can inspect, edit, archive, and delete those memories.

## Current State

The repository currently supports a local role-playing chat demo:

- TypeScript provides the CLI and browser demo.
- Python FastAPI provides the core runtime.
- Role packages are directory-based YAML files under `examples/roles`.
- Runtime config is loaded from `nanorole.config.yaml` and `.env`.
- Sessions are held in memory during runtime.
- Session export writes JSONL, but there is no durable session database.
- Prompt assembly is a simple system prompt plus current in-memory history.
- The demo UI supports role selection, chat streaming, and log viewing.

## Product Scope

This MVP supports:

- One local user.
- One selected companion role per session.
- Persistent sessions.
- Persistent messages.
- Long-term memory extraction after assistant responses.
- Memory retrieval before assistant responses.
- User-visible memory management.
- Basic relationship state.
- Basic privacy and safety policy for emotional companion use.

This MVP does not support:

- Multi-user accounts.
- Multi-role group chat.
- Game engine adapters.
- Script murder game mechanics.
- Graph RAG.
- User-uploaded knowledge bases.
- Cross-device sync.
- Production authentication.
- Hosted multi-tenant deployment.

## Core Product Principles

The companion should feel continuous, not omniscient.

The system should remember fewer things with higher quality instead of writing every user utterance into long-term memory.

The user must be able to see and control remembered information.

Memory should be grounded in source messages so incorrect memories can be debugged.

Sensitive information should not be silently stored as long-term memory.

The runtime should preserve roleplay style, but emotional companion safety has priority over staying in character.

## Architecture

The MVP adds four durable layers to the existing runtime:

- `Storage`: SQLite-backed persistence for sessions, messages, events, memories, summaries, and relationship state.
- `Memory`: extraction, merge, retrieval, source tracking, and mutation APIs.
- `Context Assembler`: prompt-time assembly of role config, recent messages, session summary, relevant memories, boundaries, and relationship state.
- `Debug UI`: browser pages for session history and memory management.

Recommended module layout:

```text
python/nanorole_runtime/src/nanorole_runtime/storage.py
python/nanorole_runtime/src/nanorole_runtime/memory.py
python/nanorole_runtime/src/nanorole_runtime/context.py
python/nanorole_runtime/src/nanorole_runtime/summaries.py
python/nanorole_runtime/src/nanorole_runtime/api.py
python/nanorole_runtime/src/nanorole_runtime/sessions.py
python/nanorole_runtime/src/nanorole_runtime/prompt.py
packages/demo/src/pages.ts
packages/demo/src/server.ts
```

`storage.py` owns database schema and low-level SQLite access.

`memory.py` owns memory types, extraction policy, merge policy, retrieval scoring, and memory mutations.

`context.py` owns prompt-time context assembly and token-budget decisions.

`summaries.py` owns rolling conversation summaries.

`sessions.py` remains the runtime orchestrator for session creation, message streaming, persistence, and memory update hooks.

`api.py` exposes session, message, memory, and debug endpoints.

`pages.ts` and `server.ts` remain the lightweight local demo, but gain session history and memory pages.

## Data Model

SQLite is the MVP storage backend.

The default database path should be:

```text
.nanorole/nanorole.sqlite3
```

Add this path to runtime config under `paths.database_path`.

### `users`

Local-only for MVP, but the model should include a user id now.

```sql
create table users (
  id text primary key,
  display_name text not null,
  created_at text not null,
  updated_at text not null
);
```

The default MVP user id is:

```text
local-user
```

### `companions`

Companions map durable state to role packages.

```sql
create table companions (
  id text primary key,
  role_id text not null,
  role_version text not null,
  display_name text not null,
  created_at text not null,
  updated_at text not null
);
```

For MVP, `companion.id` can equal the selected `role_id`.

### `sessions`

```sql
create table sessions (
  id text primary key,
  user_id text not null,
  companion_id text not null,
  role_id text not null,
  role_name text not null,
  role_version text not null,
  title text,
  status text not null,
  created_at text not null,
  updated_at text not null,
  last_message_at text
);
```

Allowed status values:

```text
active
archived
deleted
```

### `messages`

```sql
create table messages (
  id text primary key,
  session_id text not null,
  role text not null,
  content text not null,
  created_at text not null,
  ordinal integer not null
);
```

Allowed role values:

```text
system
user
assistant
tool
```

The runtime should persist user messages before model calls and assistant messages after streaming completes.

### `session_events`

```sql
create table session_events (
  id text primary key,
  session_id text,
  type text not null,
  payload_json text not null,
  created_at text not null
);
```

Events should include session creation, model request metadata, memory extraction results, memory writes, memory retrieval decisions, and errors.

### `conversation_summaries`

```sql
create table conversation_summaries (
  id text primary key,
  session_id text not null,
  covered_until_message_id text not null,
  summary text not null,
  created_at text not null,
  updated_at text not null
);
```

The MVP can keep one latest summary per session, with replacement on update.

### `memories`

```sql
create table memories (
  id text primary key,
  user_id text not null,
  companion_id text not null,
  type text not null,
  content text not null,
  importance real not null,
  confidence real not null,
  status text not null,
  created_at text not null,
  updated_at text not null,
  last_used_at text,
  use_count integer not null default 0
);
```

Allowed memory types:

```text
profile
preference
episodic
relationship
boundary
```

Allowed status values:

```text
active
archived
deleted
```

Importance and confidence should be normalized from `0.0` to `1.0`.

### `memory_sources`

```sql
create table memory_sources (
  memory_id text not null,
  message_id text not null,
  primary key (memory_id, message_id)
);
```

Every extracted memory must link to at least one source message.

### `relationship_states`

```sql
create table relationship_states (
  user_id text not null,
  companion_id text not null,
  summary text not null,
  familiarity real not null,
  trust real not null,
  preferred_address text,
  communication_style text,
  updated_at text not null,
  primary key (user_id, companion_id)
);
```

The first version should keep this simple. It should not claim emotional intimacy that has not been earned in the conversation.

## Memory Policy

Memory extraction runs after an assistant response has completed and the full user-assistant exchange is persisted.

The extractor receives:

- Recent user message.
- Assistant response.
- Current role id.
- Existing active memories likely related to the exchange.
- Current relationship state.

The extractor returns JSON:

```json
{
  "memories": [
    {
      "type": "preference",
      "content": "The user prefers gentle reminders rather than direct pressure.",
      "importance": 0.7,
      "confidence": 0.8,
      "source_message_ids": ["..."]
    }
  ],
  "archive_memory_ids": [],
  "relationship_patch": {
    "summary": "The user is building trust with the companion through regular check-ins.",
    "familiarity_delta": 0.03,
    "trust_delta": 0.02,
    "preferred_address": null,
    "communication_style": "gentle and low-pressure"
  }
}
```

The system should write memory when:

- The user explicitly states a stable fact about themselves.
- The user states a durable preference or dislike.
- The user shares an important life event.
- The user sets a boundary.
- The conversation changes the relationship state in a durable way.

The system should not write memory when:

- The information is temporary.
- The statement is ambiguous.
- The assistant inferred the fact without user confirmation.
- The information is sensitive and the user has not clearly asked the companion to remember it.
- The content is mainly transient emotion without a durable implication.

Sensitive information should be handled conservatively. The MVP should treat health details, mental health crises, sexual content, financial distress, legal issues, exact addresses, credentials, and third-party private information as sensitive. These can be mentioned in current conversation context, but should not be written as long-term memory unless the user explicitly asks.

## Memory Merge Policy

Before creating a new memory, search active memories for the same user and companion.

If the new memory repeats an existing memory, update `updated_at`, `confidence`, and source links instead of inserting a duplicate.

If the new memory contradicts an existing memory, preserve the old memory but archive it when the new statement is explicit and higher confidence.

If the new memory refines an existing memory, rewrite the existing content into a concise updated form.

Memory content should be written as durable facts, not raw chat quotes.

Good memory:

```text
The user prefers encouragement that is calm and specific.
```

Bad memory:

```text
The user said "I guess I like it when you talk softer lol".
```

## Memory Retrieval Policy

Before each model request, retrieve active memories for the session's user and companion.

The MVP can start with lexical scoring and metadata scoring. Vector search can be added later.

Recommended scoring:

```text
score = text_relevance
      + importance * 0.35
      + recency_bonus
      + boundary_bonus
      + relationship_bonus
      - overuse_penalty
```

Rules:

- `boundary` memories always get high priority when relevant.
- `relationship` memories should be included as a compact relationship summary rather than many separate facts.
- `episodic` memories should be used sparingly and only when relevant.
- Recently used memories should receive an overuse penalty to avoid repetitive callbacks.
- Retrieved memory ids should be recorded in `session_events`.
- Used memories should update `last_used_at` and `use_count`.

## Context Assembly

`prompt.py` should stop directly combining the whole in-memory history with the system prompt. Instead, `context.py` should build a structured context package.

The assembled model messages should contain:

- System instruction.
- Role package.
- Companion safety and privacy instruction.
- Relationship state.
- User boundaries.
- Relevant long-term memories.
- Current session summary.
- Recent messages.
- Current user input.

The prompt should clearly separate memory from instruction:

```text
Long-term memory facts. Treat these as fallible notes. Do not overuse them. If the user corrects one, accept the correction and update memory.
```

The companion should not mention that it used a memory unless it is natural or the user asks.

## API Changes

Add session endpoints:

```text
GET /v1/sessions
GET /v1/sessions/{sessionId}
GET /v1/sessions/{sessionId}/messages
PATCH /v1/sessions/{sessionId}
```

Add memory endpoints:

```text
GET /v1/memories?userId=local-user&companionId=<role_id>
POST /v1/memories
PATCH /v1/memories/{memoryId}
DELETE /v1/memories/{memoryId}
```

`DELETE` should soft-delete by setting status to `deleted`.

Add debug endpoint:

```text
GET /v1/sessions/{sessionId}/context-preview
```

This returns the assembled context without calling the model. It is for local debugging only.

## Demo UI Changes

The browser demo should add:

- Session list in the sidebar.
- Button to resume an existing session.
- Memory page linked from the chat header.
- Memory list grouped by type.
- Edit, archive, delete, and add memory actions.
- Source message display for each memory.
- Context preview panel for the current session.

The UI can remain local and simple. It does not need authentication, routing framework, or a build tool migration for this MVP.

## Safety and Privacy

The companion should:

- Respect explicit user boundaries.
- Avoid claiming professional medical, legal, or financial authority.
- Encourage real-world support during crisis-like conversations.
- Avoid manipulative dependency language.
- Avoid storing sensitive information silently.
- Let the user delete memory.
- Treat memory as user-controlled, not as hidden surveillance.

The MVP should include a system instruction similar to:

```text
You are an emotional companion, not a therapist, doctor, lawyer, or financial advisor. Be supportive and grounded. If the user describes imminent self-harm, harm to others, or a medical emergency, encourage contacting local emergency services or trusted real-world support. Do not intensify dependency. Respect user boundaries and corrections.
```

## Testing Strategy

Tests should cover:

- SQLite schema initialization is idempotent.
- Sessions persist across manager instances.
- Messages preserve order.
- Memory extraction output validation rejects malformed JSON.
- Memory merge avoids duplicates.
- Boundary memories are retrieved before ordinary memories.
- Deleted memories are not retrieved.
- Prompt assembly includes selected memories and excludes deleted memories.
- API memory mutation endpoints update database rows correctly.
- Demo server proxies new endpoints correctly.

Conversation quality should be tested with fixed fixtures:

- User states a stable preference and the system remembers it later.
- User shares a temporary mood and the system does not write long-term memory.
- User says "do not remember this" and no memory is written.
- User corrects an old fact and the old memory is archived.
- User deletes a memory and it is not used again.

## Rollout Plan

Milestone 1 creates durable sessions and messages.

Milestone 2 creates memory storage, manual memory CRUD, and memory debug UI.

Milestone 3 adds automatic memory extraction and merge.

Milestone 4 adds retrieval and context assembly.

Milestone 5 adds relationship state and conversation summaries.

Milestone 6 adds safety fixtures and quality regression tests.

## Future Extensions

After the MVP is stable, the same foundation can support:

- Vector retrieval for memories and lore.
- World packages.
- Multi-character sessions.
- Game NPC action outputs.
- Script murder clues and hidden knowledge.
- Graph RAG over people, places, events, and relationships.
- External chat adapters.

The extension order should be driven by product traction. For emotional companion use, memory correctness and user control matter more than Graph RAG.

## Self-Review

This design is intentionally scoped to single-user, single-companion long-memory chat.

It does not depend on external services beyond the configured OpenAI-compatible model provider.

It avoids Graph RAG and multi-role orchestration until the persistence and memory foundation exists.

It defines durable data models, APIs, UI surface, safety constraints, and test targets with enough detail for implementation planning.
