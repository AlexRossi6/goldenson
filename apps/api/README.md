# GoldenSon API

FastAPI backend for GoldenSon's local workspace, retrieval, managed Ollama, and
approval-gated agent.

## Current capabilities

- Workspace, page, block, and file APIs with optimistic concurrency
- Hybrid keyword and local semantic retrieval with source provenance
- Recoverable page and UTF-8 text-file indexing with health and retry endpoints
- Managed loopback Ollama runtime and model selection
- Streaming, approval-gated agent runs with explicit tools and a sanitized audit trail
- Workspace-scoped filesystem storage through a `StorageProvider` abstraction

PDFs and other binary files are stored locally and searchable by filename and
metadata, but their contents are not parsed. Supported UTF-8 text files are indexed
separately so indexing failures never block file CRUD.

## Development

```bash
uv sync
uv run alembic upgrade head
uv run uvicorn goldenson_api.main:app --app-dir src --reload
```

The `--app-dir src` option is required when the package is not installed in editable
mode. The API health endpoint is available at `/api/health`; OpenAPI documentation
is available at `/docs`.

## Local semantic indexing

Semantic indexing uses Ollama's local `/api/embed` endpoint. It is disabled until
`GOLDENSON_EMBEDDING_MODEL` is explicitly configured; keyword retrieval remains
available without it. GoldenSon never downloads an embedding model or falls back
to a cloud provider. Install the chosen embedding model in Ollama first, then set
the environment variable before starting the API.

## Database

Run migrations:

```bash
uv run alembic upgrade head
```

Create a new migration after model changes:

```bash
uv run alembic revision --autogenerate -m "describe change"
```

Seed development data:

```bash
uv run python -m goldenson_api.scripts.seed
```

## Checks

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy .
uv run pytest
```

Agent runs and tool calls are persisted in SQLite. READ tools execute directly;
WRITE and DESTRUCTIVE tools require explicit approval and resume the persisted run
after the decision. Tool inputs are validated and agent access remains restricted
to workspace-scoped services.
