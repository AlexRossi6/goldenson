# GoldenSon

GoldenSon is an open-source, fully local AI knowledge workspace. It combines a
document editor, local files, workspace retrieval, and an approval-gated AI agent
without requiring a cloud account or sending workspace data to a cloud provider.

The project is an active MVP. The core workspace and local agent are implemented;
the broader direction is described in [docs/vision.md](docs/vision.md).

## What works today

- Local workspaces with nested pages and block-based editing
- Paragraph, heading, checklist, code, quote, and divider blocks
- Local file uploads and page attachments
- Hybrid keyword and semantic retrieval across pages and blocks
- Filename search for all files and content search for supported UTF-8 text files
- Recoverable page and file indexing with visible health and retry controls
- Evidence-based related content with previews and navigation to matching blocks
- Managed local AI through Ollama with an `LLMProvider` abstraction
- Streaming assistant responses with retrieved source references
- Validated agent tools for search, reading, structured queries, pages, tasks, and files
- Mandatory approval for every WRITE and DESTRUCTIVE agent action
- Persistent agent runs that pause for approval and resume the same reasoning loop
- Reconnect, cancellation, execution limits, and a sanitized audit trail
- Immediate UI refresh after approved agent mutations through TanStack Query
- Optimistic concurrency for mutable pages and blocks

All workspace data, SQLite records, files, retrieval, conversations, and inference
stay on the user's machine by default. GoldenSon does not silently fall back to a
cloud model and does not include telemetry.

## Vision

GoldenSon aims to become a personal knowledge system that AI can understand,
analyze, and safely operate on, rather than a notes application with a chatbot
attached. The long-term direction includes richer relationships, proactive
insights, advanced agents, and explicit opt-in integrations.

Those items are direction, not current functionality. See
[docs/vision.md](docs/vision.md) for the full roadmap.

## Architecture

```text
React + TypeScript + Vite
	  |
       FastAPI
	  |
services / repositories / providers
	  |
 SQLite + local filesystem + Ollama
```

- **Frontend:** React, TypeScript, Vite, TanStack Query, Zustand
- **Backend:** Python 3.12+, FastAPI, Pydantic, SQLAlchemy, Alembic, SQLite
- **Local AI:** Ollama through an OpenAI-compatible provider interface
- **Storage:** A workspace-scoped `StorageProvider` with a local filesystem implementation
- **Tooling:** pnpm, uv, Ruff, mypy, pytest, Vitest, Oxlint

The agent never receives unrestricted shell, SQL, HTTP, or filesystem access.
Tool arguments are validated, filesystem access is workspace-scoped, database
queries are structured, and all mutations require explicit approval.

## Repository layout

```text
apps/api/   FastAPI backend, migrations, and backend tests
apps/web/   React application and frontend tests
docs/       Product vision and design documents
```

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- Node.js 20+
- [pnpm](https://pnpm.io/)
- Ollama, or macOS for GoldenSon's managed Ollama installation flow

## Run locally

Install dependencies and prepare the database:

```bash
cd apps/api
uv sync
uv run alembic upgrade head
```

Start the API from `apps/api`:

```bash
uv run uvicorn goldenson_api.main:app --app-dir src --reload --host 127.0.0.1 --port 8000
```

The `--app-dir src` option is required because the backend uses a `src/` layout.
The API health endpoint is `http://127.0.0.1:8000/api/health` and interactive API
documentation is available at `http://127.0.0.1:8000/docs`.

In another terminal, start the frontend:

```bash
cd apps/web
pnpm install
pnpm dev
```

Open the URL printed by Vite, normally `http://127.0.0.1:5173`. The development
server proxies `/api` to the API on port `8000`.

Development data is optional:

```bash
cd apps/api
uv run python -m goldenson_api.scripts.seed
```

## Local AI

GoldenSon detects a loopback Ollama runtime and manages supported model downloads
and selection from the Local AI panel. On macOS, GoldenSon can install the official
signed Ollama application into its private runtime directory. It does not install
models automatically during project setup.

Relevant defaults are documented in [.env.example](.env.example):

```bash
GOLDENSON_OLLAMA_BASE_URL=http://127.0.0.1:11434
GOLDENSON_OLLAMA_RUNTIME_ROOT=~/.goldenson/runtime
GOLDENSON_EMBEDDING_MODEL=
GOLDENSON_KNOWLEDGE_INDEX_TIMEOUT_SECONDS=90
GOLDENSON_AGENT_MAX_TOOL_CALLS=8
GOLDENSON_AGENT_MAX_RUN_SECONDS=60
GOLDENSON_AGENT_PROVIDER_TIMEOUT_SECONDS=45
GOLDENSON_AGENT_TOOL_TIMEOUT_SECONDS=10
```

The Ollama endpoint must resolve to loopback. Provider requests explicitly disable
model reasoning where supported (`think: false`, `reasoning_effort: none`).

Semantic retrieval is enabled only when `GOLDENSON_EMBEDDING_MODEL` names an
embedding model already installed in Ollama. Without it, keyword retrieval remains
available. GoldenSon never downloads an embedding model or falls back to a cloud
provider automatically.

File content search currently accepts bounded UTF-8 text. PDFs and other binary
formats are stored locally and remain searchable by filename and metadata, but
their contents are not parsed yet.

## Agent lifecycle

```text
request -> retrieval -> local model -> proposed tool call
	-> approval -> execution -> resumed reasoning -> result
```

READ tools execute without approval. WRITE and DESTRUCTIVE tools pause the persisted
run until the user approves or rejects the proposal. Approved mutations immediately
invalidate the relevant frontend queries, so page, block, and file views update
without a browser reload.

Straightforward commands such as `Create a page called Research` are parsed into a
validated proposal immediately, while still using the same approval, audit,
execution, and resumption path.

## Quality checks

Backend:

```bash
cd apps/api
uv run ruff check .
uv run ruff format --check .
uv run mypy .
uv run pytest
```

Frontend:

```bash
cd apps/web
pnpm lint
pnpm typecheck
pnpm test
pnpm build
```

CI runs these checks for pushes and pull requests through
`.github/workflows/ci.yml`.

## Project status

GoldenSon is under active development and is not yet packaged as a desktop
application. Current work is focused on making the local knowledge workspace and
its controlled agent dependable before expanding into richer document parsing,
background workflows, integrations, or synchronization.
