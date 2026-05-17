# Nanorole

Nanorole is a local role-playing agent demo. A developer describes a character in a directory-based YAML role package, then chats with that role through a TypeScript demo UI backed by a small Python core runtime.

## Quick Start

1. Install dependencies:

```powershell
corepack yarn install
```

```powershell
cd python/nanorole_runtime
uv sync
```

2. Configure credentials:

```powershell
Copy-Item .env.example .env
```

Edit `.env` and set `DEEPSEEK_API_KEY`. The default config points to DeepSeek's OpenAI-compatible Chat Completions endpoint.

3. Start the browser demo:

```powershell
corepack yarn demo
```

Open `http://127.0.0.1:3000/chat` for browser-based role chat. The same demo server exposes `http://127.0.0.1:3000/logs` for the JSONL log viewer.
Use `http://127.0.0.1:3000/memories` to inspect, add, edit, archive, delete, and preview companion memories.

The demo command cleans old local demo/core processes, builds the TypeScript packages, starts the Python core runtime on `127.0.0.1:8765`, then starts the TypeScript demo server on `127.0.0.1:3000`.

The command-line chat still exists for quick checks:

```powershell
corepack yarn build
corepack yarn workspace @nanorole/cli node dist/index.js chat examples/roles/clockwork-sage
```

## Role Package

Role packages are directories with a `character.yaml` file. Required fields are `id`, `name`, `version`, `world`, `background`, `persona`, `goals`, and `opening`. Optional fields are `style`, `safety_rules`, and `metadata`. Model selection is runtime configuration, not role content.

## Core Runtime API

Python is core-only. It does not serve the demo UI or log viewer.

- `GET /health`
- `POST /v1/sessions`
- `GET /v1/sessions`
- `GET /v1/sessions/{sessionId}`
- `GET /v1/sessions/{sessionId}/messages`
- `POST /v1/sessions/{sessionId}/messages:stream`
- `GET /v1/sessions/{sessionId}/context-preview`
- `GET /v1/sessions/{sessionId}/export`
- `GET /v1/memories`
- `POST /v1/memories`
- `PATCH /v1/memories/{memoryId}`
- `DELETE /v1/memories/{memoryId}`

Session history and companion memories are stored locally in `.nanorole/nanorole.sqlite3`. Export returns JSONL and also writes `.nanorole/sessions/<sessionId>.jsonl`. Runtime logs are JSONL in `.nanorole/logs/runtime.jsonl`; completed requests include the user input, model messages, assistant output, duration, and token chunk count. The TypeScript demo reads that JSONL directly for its log viewer.

## Companion Memory MVP

Nanorole stores local memories in `.nanorole/nanorole.sqlite3`.
Users can inspect, edit, archive, and delete memories from the demo UI.
The companion treats memory as fallible user-controlled notes.
Sensitive information should not be stored unless the user explicitly asks the companion to remember it.

## Tests

```powershell
cd python/nanorole_runtime
uv run pytest
```

```powershell
corepack yarn test
```
