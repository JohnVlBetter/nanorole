# Nanorole

Nanorole is a local role-playing agent demo. A developer describes a character in a directory-based YAML role package, then chats with that role through a TypeScript CLI backed by a local Python FastAPI runtime.

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

3. Build and run:

```powershell
corepack yarn build
corepack yarn workspace @nanorole/cli node dist/index.js chat examples/roles/clockwork-sage
```

The CLI starts or reuses a local Nanorole runtime on the configured port, prints the role opening, and streams replies through SSE.

## Role Package

Role packages are directories with a `character.yaml` file. Required fields are `id`, `name`, `version`, `world`, `background`, `persona`, `goals`, and `opening`. Optional fields are `style`, `safety_rules`, and `metadata`. Model selection is runtime configuration, not role content.

## Runtime API

- `GET /health`
- `POST /v1/sessions`
- `POST /v1/sessions/{sessionId}/messages:stream`
- `GET /v1/sessions/{sessionId}/export`

Session history is in memory. Export returns JSONL and also writes `.nanorole/sessions/<sessionId>.jsonl`. Runtime logs are JSONL in `.nanorole/logs/runtime.jsonl`. Full prompt traces are only logged when `logging.trace_requests: true` or CLI `--debug` is enabled.

## Tests

```powershell
cd python/nanorole_runtime
uv run pytest
```

```powershell
corepack yarn test
```
